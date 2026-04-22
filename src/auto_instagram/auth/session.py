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

    Uses multiple signals: URL didn't redirect to login/challenge, and the
    navbar's profile avatar is present.
    """
    await page.goto(INSTAGRAM_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle", timeout=10_000)

    current = page.url
    log.debug("current URL after navigation: %s", current)

    for marker in CHALLENGE_URL_MARKERS:
        if marker in current:
            return False

    # The authenticated feed always has a Home nav link with aria-label.
    try:
        await page.locator('a[href="/"][aria-label*="Home" i]').first.wait_for(
            state="visible", timeout=5_000
        )
        return True
    except Exception:
        return False


async def detect_challenge(page: Page) -> None:
    """Raise ChallengeRequiredError if the current page is a challenge/login redirect."""
    current = page.url
    for marker in CHALLENGE_URL_MARKERS:
        if marker in current:
            raise ChallengeRequiredError(
                f"Instagram redirected to {current}. "
                "Re-authenticate with `auto-ig login` and retry."
            )
