"""The Playwright-web-driven publisher: opens instagram.com with a saved
session, clicks through the Create modal, uploads media, writes caption,
and clicks Share.

Stories are not supported (the web UI does not create them).
"""
from __future__ import annotations

import asyncio
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ..auth.session import (
    ChallengeRequiredError,
    NotAuthenticatedError,
    detect_challenge,
    dismiss_popups,
    is_logged_in,
)
from ..browser.factory import launch_context
from ..config import AccountConfig, PacingSettings
from ..content.models import Post, PostType
from ..utils.logging import get_logger
from .base import PublishResult
from .selectors import (
    CAPTION_TEXTAREA_ALTERNATIVES,
    CREATE_DIRECT_URL,
    CREATE_FILE_INPUT,
    MODAL_NEXT_BUTTON_TEXT,
    MODAL_SHARE_BUTTON_TEXT,
    POST_SHARED_TEXT_ALTERNATIVES,
    REEL_OK_BUTTON_TEXT,
)

if TYPE_CHECKING:
    from patchright.async_api import Locator, Page

log = get_logger(__name__)


class PlaywrightWebPublisher:
    """Publishes a Post by driving instagram.com."""

    def __init__(self, account: AccountConfig, session_file: Path) -> None:
        self.account = account
        self.session_file = session_file
        self._pacing = account.pacing

    async def healthcheck(self) -> bool:
        if not self.session_file.exists():
            return False
        async with launch_context(self.account, self.session_file) as ctx:
            page = await ctx.new_page()
            return await is_logged_in(page)

    async def publish(self, post: Post, *, dry_run: bool = False) -> PublishResult:
        if not self.session_file.exists():
            raise NotAuthenticatedError(
                f"No session file at {self.session_file}. "
                "Run `auto-ig login` or `auto-ig import-cookies` first."
            )

        async with launch_context(self.account, self.session_file) as ctx:
            page = await ctx.new_page()

            if not await is_logged_in(page):
                raise NotAuthenticatedError(
                    "Session appears invalid. Re-authenticate with `auto-ig login`."
                )
            await dismiss_popups(page)

            await _pre_run_idle(page, self._pacing)
            try:
                result = await self._run_flow(page, post, dry_run=dry_run)
            except ChallengeRequiredError:
                raise
            except Exception as e:
                await detect_challenge(page)
                raise RuntimeError(f"Publish failed: {e}") from e
            return result

    async def _run_flow(
        self, page: Page, post: Post, *, dry_run: bool
    ) -> PublishResult:
        log.info("Opening Create page for %s (%s)", post.source_dir.name, post.type.value)

        # Directly navigating to /create/select/ is more robust than clicking
        # the sidebar "New post" button — the sidebar is a JS-handler tangle
        # that resists synthetic clicks, while the route exposes the file input
        # immediately. Works for feed, carousel, and Reel uploads alike: IG
        # picks the path from the media type after upload.
        await page.goto(CREATE_DIRECT_URL, wait_until="domcontentloaded")
        await _humanize_delay(self._pacing)

        file_input = page.locator(CREATE_FILE_INPUT).first
        await file_input.wait_for(state="attached", timeout=15_000)
        await file_input.set_input_files([str(p) for p in post.media])
        log.info("Uploaded %d file(s)", len(post.media))
        await _humanize_delay(self._pacing)

        # For Reels, IG sometimes surfaces a modal "Video will be shared as a Reel. OK".
        if post.type == PostType.REEL:
            await _click_button_by_text_optional(page, REEL_OK_BUTTON_TEXT, timeout_ms=4000)

        # Crop/edit step → Next
        await _click_button_by_text(page, MODAL_NEXT_BUTTON_TEXT, label="Next (crop)")
        await _humanize_delay(self._pacing)

        # Filter/edit step → Next (only for image posts; Reels may skip this)
        await _click_button_by_text_optional(page, MODAL_NEXT_BUTTON_TEXT, timeout_ms=6000)
        await _humanize_delay(self._pacing)

        # Caption step
        await _fill_caption(page, post.caption)
        await _humanize_delay(self._pacing)

        if dry_run:
            log.warning("Dry-run: reached Share button but NOT clicking. Aborting.")
            return PublishResult(ok=True, dry_run=True)

        await _click_button_by_text(page, MODAL_SHARE_BUTTON_TEXT, label="Share")
        log.info("Share clicked; waiting for confirmation...")

        shortcode = await _wait_for_share_confirmation(page, timeout_ms=120_000)
        url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else None
        return PublishResult(ok=True, shortcode=shortcode, url=url)


# ---------- helpers ----------


async def _pre_run_idle(page: Page, pacing: PacingSettings) -> None:
    """Scroll/dwell a bit before doing anything — IG's ML model watches for
    click-without-context behavior."""
    delay = random.uniform(pacing.pre_run_idle_seconds_min, pacing.pre_run_idle_seconds_max)
    log.debug("Pre-run idle %.1fs", delay)
    try:
        # Gentle scroll pulses.
        end_at = asyncio.get_event_loop().time() + delay
        while asyncio.get_event_loop().time() < end_at:
            await page.mouse.wheel(0, random.randint(100, 600))
            await asyncio.sleep(random.uniform(1.5, 4.0))
    except Exception:
        await asyncio.sleep(delay)


async def _humanize_delay(pacing: PacingSettings) -> None:
    delay = random.uniform(pacing.min_step_delay_seconds, pacing.max_step_delay_seconds)
    log.debug("Humanized step delay %.1fs", delay)
    await asyncio.sleep(delay)


async def _click_first(page: Page, selectors: list[str], *, label: str) -> None:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=5_000)
            await loc.click()
            log.debug("Clicked %s via selector %s", label, sel)
            return
        except Exception:
            continue
    raise TimeoutError(f"Could not locate {label}. Selectors tried: {selectors}")


async def _click_first_optional(
    page: Page, selectors: list[str], *, label: str, timeout_ms: int
) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=timeout_ms)
            await loc.click()
            log.debug("Clicked optional %s via selector %s", label, sel)
            return True
        except Exception:
            continue
    log.debug("Optional %s not present; skipping.", label)
    return False


async def _click_button_by_text(page: Page, text: str, *, label: str) -> None:
    loc: Locator = page.get_by_role("button", name=text).first
    try:
        await loc.wait_for(state="visible", timeout=15_000)
    except Exception:
        # Fallback: IG sometimes renders "buttons" as div[role=button] which
        # get_by_role handles, but in rare cases the text is inside a <div role="button">
        # without proper role; try a tagless fallback.
        loc = page.locator(f'div[role="button"]:has-text("{text}")').first
        await loc.wait_for(state="visible", timeout=5_000)
    await loc.click()
    log.debug("Clicked %s (%s)", label, text)


async def _click_button_by_text_optional(
    page: Page, text: str, *, timeout_ms: int
) -> bool:
    loc: Locator = page.get_by_role("button", name=text).first
    try:
        await loc.wait_for(state="visible", timeout=timeout_ms)
        await loc.click()
        return True
    except Exception:
        return False


async def _fill_caption(page: Page, caption: str) -> None:
    if not caption:
        return
    for sel in CAPTION_TEXTAREA_ALTERNATIVES:
        loc = page.locator(sel).first
        try:
            await loc.wait_for(state="visible", timeout=8_000)
            await loc.click()
            # Type slowly to simulate human input.
            await loc.type(caption, delay=random.randint(15, 45))
            log.debug("Caption filled via selector %s", sel)
            return
        except Exception:
            continue
    raise TimeoutError("Could not locate caption textarea.")


async def _wait_for_share_confirmation(page: Page, *, timeout_ms: int) -> str | None:
    """Wait for IG's 'your post has been shared' acknowledgement, then try
    to extract the media shortcode from whatever link it surfaces or the
    current URL if it redirects."""
    import asyncio as _asyncio

    deadline = _asyncio.get_event_loop().time() + timeout_ms / 1000
    while _asyncio.get_event_loop().time() < deadline:
        # Confirmation text in the modal
        for msg in POST_SHARED_TEXT_ALTERNATIVES:
            if await page.get_by_text(msg).first.is_visible():
                # Try to find an anchor to /p/<shortcode>/ or /reel/<shortcode>/
                anchor = page.locator('a[href*="/p/"], a[href*="/reel/"]').first
                try:
                    href = await anchor.get_attribute("href", timeout=2_000)
                    if href:
                        m = re.search(r"/(?:p|reel)/([^/?]+)/", href)
                        if m:
                            return m.group(1)
                except Exception:
                    pass
                return None
        await _asyncio.sleep(1.0)

    raise TimeoutError("Timed out waiting for share confirmation.")
