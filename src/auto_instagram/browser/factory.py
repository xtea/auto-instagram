"""Launch Patchright (default) or Camoufox with anti-detection settings and
load an account's stored session cookies.

Patchright is a drop-in async Playwright replacement that patches CDP / webdriver
leaks at the binary level. Vanilla `playwright` is not used because Instagram
detects it in 2026.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import AccountConfig

if TYPE_CHECKING:
    from patchright.async_api import Browser, BrowserContext, Page


@asynccontextmanager
async def launch_context(
    account: AccountConfig,
    session_file: Path | None,
) -> AsyncIterator[BrowserContext]:
    """Launch a browser + context matching `account`.

    Loads `session_file` (Playwright storage_state) if it exists, otherwise
    starts a clean context (used by `auto-ig login`).
    """
    if account.browser == "patchright":
        async with _patchright_context(account, session_file) as ctx:
            yield ctx
    elif account.browser == "camoufox":  # pragma: no cover - optional extra
        async with _camoufox_context(account, session_file) as ctx:
            yield ctx
    else:
        raise ValueError(f"Unknown browser: {account.browser}")


@asynccontextmanager
async def _patchright_context(
    account: AccountConfig,
    session_file: Path | None,
) -> AsyncIterator[BrowserContext]:
    from patchright.async_api import async_playwright

    proxy_kw: dict[str, object] | None = None
    if account.proxy:
        proxy_kw = {"server": account.proxy.server}
        if account.proxy.bypass:
            proxy_kw["bypass"] = account.proxy.bypass
        if account.proxy.username:
            proxy_kw["username"] = account.proxy.username
        if account.proxy.password:
            proxy_kw["password"] = account.proxy.password

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=account.headless,
            channel="chrome",  # real Chrome channel has fewer fingerprint deltas
        )
        context_kwargs: dict[str, object] = {
            "user_agent": account.user_agent,
            "viewport": {
                "width": account.viewport.width,
                "height": account.viewport.height,
            },
            "locale": account.locale,
            "timezone_id": account.timezone,
        }
        if proxy_kw is not None:
            context_kwargs["proxy"] = proxy_kw
        if session_file and session_file.exists():
            context_kwargs["storage_state"] = str(session_file)

        context = await browser.new_context(**context_kwargs)
        try:
            yield context
        finally:
            await context.close()
            await browser.close()


@asynccontextmanager
async def _camoufox_context(
    account: AccountConfig,
    session_file: Path | None,
) -> AsyncIterator[BrowserContext]:  # pragma: no cover - optional extra
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as e:
        raise ImportError(
            "Camoufox is not installed. Install with: pip install 'auto-instagram[camoufox]'"
        ) from e

    launch_kw: dict[str, object] = {
        "headless": account.headless,
        "locale": account.locale,
        "os": ["macos", "windows", "linux"],
    }
    if account.proxy:
        launch_kw["proxy"] = {"server": account.proxy.server}

    async with AsyncCamoufox(**launch_kw) as browser:
        context_kwargs: dict[str, object] = {
            "user_agent": account.user_agent,
            "viewport": {
                "width": account.viewport.width,
                "height": account.viewport.height,
            },
            "locale": account.locale,
            "timezone_id": account.timezone,
        }
        if session_file and session_file.exists():
            context_kwargs["storage_state"] = str(session_file)
        context = await browser.new_context(**context_kwargs)
        try:
            yield context
        finally:
            await context.close()


async def save_storage_state(context: BrowserContext, session_file: Path) -> None:
    """Persist the current context's cookies + localStorage to disk."""
    session_file.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(session_file))


async def new_page(context: BrowserContext) -> Page:
    return await context.new_page()
