"""Headed manual login flow — opens a real browser window for the user to
log in (handling 2FA themselves), then saves storage_state JSON."""
from __future__ import annotations

from pathlib import Path

from ..browser.factory import launch_context, save_storage_state
from ..config import AccountConfig
from ..utils.logging import get_logger
from .session import INSTAGRAM_URL, is_logged_in

log = get_logger(__name__)


async def run_login(account: AccountConfig, session_file: Path) -> None:
    """Open IG in a headed window and wait for the user to complete login,
    then persist the session to `session_file`.

    The user may hit 2FA, captchas, or "Save login info?" prompts. We
    detect login by polling `is_logged_in` every few seconds until it
    returns True or the user closes the window.
    """
    if account.headless:
        log.warning("Forcing headed mode for login flow regardless of config.")
    # Temporarily flip headless off; login requires user interaction.
    runtime = account.model_copy(update={"headless": False})

    async with launch_context(runtime, session_file=None) as context:
        page = await context.new_page()
        await page.goto(INSTAGRAM_URL + "accounts/login/", wait_until="domcontentloaded")
        log.info(
            "A browser window opened. Log in to Instagram manually "
            "(complete 2FA if prompted). The session will be saved automatically "
            "once you reach the home feed."
        )

        # Poll for authenticated state. 10-minute window.
        import asyncio

        deadline = asyncio.get_event_loop().time() + 600
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(3)
            try:
                if await is_logged_in(page):
                    await save_storage_state(context, session_file)
                    log.info("Login captured. Session saved to %s", session_file)
                    return
            except Exception as e:
                log.debug("login poll: %s", e)

        raise TimeoutError("Timed out waiting for manual login (10 min).")
