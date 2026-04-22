"""Session state checks: logged-in detection, challenge detection."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from patchright.async_api import Page

log = get_logger(__name__)

INSTAGRAM_URL = "https://www.instagram.com/"

# URL substrings that indicate IG is blocking us from posting
CHALLENGE_URL_MARKERS = (
    "/challenge/",
    "/accounts/login/",
    "/accounts/suspended/",
    "/accounts/onetap/",
)

# sessionid cookie is only set when authenticated
SESSION_COOKIE_NAMES = {"sessionid", "ds_user_id"}


class ChallengeRequiredError(RuntimeError):
    """Instagram issued a checkpoint / challenge / login redirect. Manual action needed."""


class NotAuthenticatedError(RuntimeError):
    """No valid session; user must run `auto-ig login` or `import-cookies`."""


async def is_logged_in(page: Page) -> bool:
    """Navigate to instagram.com and confirm we landed on the authenticated feed.

    Avoids wait_for_load_state('networkidle') — instagram.com holds long-polling
    connections open indefinitely. After the DOM is ready we dismiss IG's
    recurring popups ("Save your login info?", "Turn on notifications", app
    install prompt), then confirm the Home nav link is visible.
    """
    await page.goto(INSTAGRAM_URL, wait_until="domcontentloaded")

    current = page.url
    log.debug("current URL after navigation: %s", current)
    for marker in CHALLENGE_URL_MARKERS:
        if marker in current:
            return False

    # Give IG a moment to render the "Save login info" popup before dismissing it.
    import asyncio as _asyncio
    await _asyncio.sleep(2.0)
    await dismiss_popups(page)

    try:
        # Any of these aria-labels only exist on the authenticated feed chrome.
        await page.locator(
            '[aria-label="Home"], [aria-label="New post"], a[href="/direct/inbox/"]'
        ).first.wait_for(state="visible", timeout=15_000)
        return True
    except Exception:
        for marker in CHALLENGE_URL_MARKERS:
            if marker in page.url:
                return False
        return False


# Texts of the dismiss buttons IG shows on first visit / post-login.
_POPUP_DISMISS_TEXTS = (
    "Not Now",
    "Not now",
    "Dismiss",
    "Close",
    "Cancel",
)


async def dismiss_popups(page: Page, *, rounds: int = 3) -> int:
    """Click through any 'Not Now' / 'Dismiss' popups IG stacks on the feed.
    Returns the number of popups dismissed. Safe to call when none are present.
    """
    dismissed = 0
    for _ in range(rounds):
        clicked_this_round = False
        for text in _POPUP_DISMISS_TEXTS:
            loc = page.get_by_role("button", name=text).first
            try:
                if await loc.is_visible(timeout=1_500):
                    await loc.click()
                    dismissed += 1
                    clicked_this_round = True
                    log.debug("dismissed popup via '%s'", text)
                    break
            except Exception:
                continue
        if not clicked_this_round:
            break
    return dismissed


async def detect_challenge(page: Page) -> None:
    """Raise ChallengeRequiredError if the current page is a challenge/login redirect."""
    current = page.url
    for marker in CHALLENGE_URL_MARKERS:
        if marker in current:
            raise ChallengeRequiredError(
                f"Instagram redirected to {current}. "
                "Re-authenticate with `auto-ig login` and retry."
            )
