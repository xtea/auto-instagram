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
from .profile import (
    captions_match,
    detect_own_handle,
    fetch_post_caption,
    first_post_href,
    shortcode_from_href,
)
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
    from patchright.async_api import BrowserContext, Locator, Page

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

    async def publish(
        self, post: Post, *, dry_run: bool = False, force: bool = False
    ) -> PublishResult:
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

            handle = await detect_own_handle(page) or self.account.handle
            log.info("Publishing as @%s", handle)

            pre_shortcode = await self._dedup_guard(ctx, handle, post, force=force)
            if pre_shortcode == _ALREADY_PUBLISHED:
                return PublishResult(
                    ok=True,
                    already_published=True,
                    shortcode=self._last_seen_shortcode,
                    url=(
                        f"https://www.instagram.com/p/{self._last_seen_shortcode}/"
                        if self._last_seen_shortcode
                        else None
                    ),
                )

            await _pre_run_idle(page, self._pacing)
            try:
                result = await self._run_flow(
                    ctx, page, post, handle=handle, pre_shortcode=pre_shortcode, dry_run=dry_run
                )
            except ChallengeRequiredError:
                raise
            except Exception as e:
                await detect_challenge(page)
                raise RuntimeError(f"Publish failed: {e}") from e
            return result

    _last_seen_shortcode: str | None = None

    async def _dedup_guard(
        self,
        ctx: BrowserContext,
        handle: str,
        post: Post,
        *,
        force: bool,
    ) -> str | None | object:
        """Return the current most-recent shortcode, or the `_ALREADY_PUBLISHED`
        sentinel if the latest post's caption matches the incoming caption
        (and `force` is False). Used both as a dedup check and to record the
        pre-publish marker for shortcode-delta confirmation."""
        check_page = await ctx.new_page()
        try:
            href = await first_post_href(check_page, handle)
            sc = shortcode_from_href(href)
            if not sc:
                log.debug("No existing posts on profile; dedup skipped.")
                return None

            if force:
                log.debug("--force: skipping dedup check.")
                return sc

            if not post.caption:
                # Without a caption we can't reliably dedup; fall through.
                return sc

            latest_caption = await fetch_post_caption(check_page, sc)
            if captions_match(latest_caption, post.caption):
                log.warning(
                    "Latest post (shortcode %s) already has this exact caption; "
                    "treating as already-published. Use --force to override.",
                    sc,
                )
                self._last_seen_shortcode = sc
                return _ALREADY_PUBLISHED
            return sc
        finally:
            await check_page.close()

    async def _run_flow(
        self,
        ctx: BrowserContext,
        page: Page,
        post: Post,
        *,
        handle: str,
        pre_shortcode: str | None | object,
        dry_run: bool,
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
        log.info("Share clicked; confirming publish...")

        pre_sc = pre_shortcode if isinstance(pre_shortcode, str) else None
        shortcode = await _confirm_publish(
            page, ctx, handle=handle, pre_shortcode=pre_sc, timeout_ms=180_000
        )
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


async def _confirm_publish(
    page: Page,
    ctx: BrowserContext,
    *,
    handle: str,
    pre_shortcode: str | None,
    timeout_ms: int,
) -> str | None:
    """Confirm that Share actually landed the post.

    Two signals, either of which is sufficient:

    1. **Fast path:** IG's 'your post has been shared' banner — the existing
       text selectors; when they render we also try to read the shortcode
       from a nearby link.
    2. **Authoritative path:** the user's profile grid advanced — the first
       post's shortcode differs from the `pre_shortcode` we recorded before
       clicking Share. This runs in a separate page so the create modal is
       not disturbed.

    The profile check starts after a brief grace period (IG sometimes needs
    a few seconds to surface the new post on the grid) and repeats until the
    deadline. A final profile check runs at deadline as a last-ditch
    recovery before giving up.
    """
    loop = asyncio.get_event_loop()
    start = loop.time()
    deadline = start + timeout_ms / 1000
    grace_until = start + 8.0

    while loop.time() < deadline:
        text_hit, text_sc = await _try_text_confirmation(page)
        if text_sc:
            return text_sc
        # Either the text banner was shown (but no shortcode available) or we
        # are past the grace period — either way, do an authoritative profile
        # check and return if the grid advanced.
        if text_hit or loop.time() > grace_until:
            sc = await _profile_delta(ctx, handle, pre_shortcode)
            if sc:
                return sc
            if text_hit:
                # Banner appeared but the grid hasn't caught up yet; retry
                # briefly then come back.
                await asyncio.sleep(3.0)
                sc = await _profile_delta(ctx, handle, pre_shortcode)
                if sc:
                    return sc
        await asyncio.sleep(2.0)

    # Final shot: give the profile one more check in case the feed was slow.
    sc = await _profile_delta(ctx, handle, pre_shortcode)
    if sc:
        return sc
    raise TimeoutError(
        "Share confirmation not detected (neither the in-modal banner nor a new post on the profile)."
    )


async def _try_text_confirmation(page: Page) -> tuple[bool, str | None]:
    """Check IG's 'shared' banner. Returns (banner_visible, shortcode_if_found)."""
    for msg in POST_SHARED_TEXT_ALTERNATIVES:
        try:
            if await page.get_by_text(msg).first.is_visible(timeout=500):
                anchor = page.locator('a[href*="/p/"], a[href*="/reel/"]').first
                try:
                    href = await anchor.get_attribute("href", timeout=1_500)
                    if href:
                        m = re.search(r"/(?:p|reel)/([^/?]+)/", href)
                        if m:
                            return True, m.group(1)
                except Exception:
                    pass
                return True, None
        except Exception:
            continue
    return False, None


async def _profile_delta(
    ctx: BrowserContext, handle: str, pre_shortcode: str | None
) -> str | None:
    """Open a scratch page, check the profile's first shortcode; return it
    only if it differs from pre_shortcode."""
    probe = await ctx.new_page()
    try:
        href = await first_post_href(probe, handle, timeout_ms=8_000)
        sc = shortcode_from_href(href)
        if sc and sc != pre_shortcode:
            return sc
        return None
    finally:
        await probe.close()


# Sentinel used internally; never leaves this module.
_ALREADY_PUBLISHED = object()
