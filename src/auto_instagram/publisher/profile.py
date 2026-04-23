"""Helpers for verifying posts before and after publishing.

The core idea: the user's own profile grid (`/<handle>/`) is the most
stable IG surface we have. The first thumbnail is always the most recent
post, and its href contains the shortcode. We use that for two things:

1. Pre-publish dedup — fetch the latest post's caption and bail if it
   matches the caption we're about to publish (the previous run
   probably succeeded but its confirmation timed out).
2. Post-publish verification — compare the latest shortcode before and
   after clicking Share. A delta is the authoritative success signal,
   regardless of whether IG's "your post has been shared" text appears.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from patchright.async_api import Page

log = get_logger(__name__)

_SHORTCODE_RE = re.compile(r"/(?:p|reel)/([^/?]+)/")
# Extracts the caption from IG's og:description:
#   '0 likes, 0 comments - handle on April 23, 2026: "CAPTION". '
_OG_CAPTION_RE = re.compile(r': "(.*)"\.?\s*$', re.DOTALL)


def shortcode_from_href(href: str | None) -> str | None:
    if not href:
        return None
    m = _SHORTCODE_RE.search(href)
    return m.group(1) if m else None


def normalize_caption(s: str | None) -> str:
    """Collapse whitespace + case-fold for comparison. Empty / None → ''."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip().casefold()


def captions_match(a: str | None, b: str | None) -> bool:
    na, nb = normalize_caption(a), normalize_caption(b)
    return bool(na) and na == nb


def extract_caption_from_og(og: str | None) -> str | None:
    """IG's og:description is always `<stats> - <handle> on <date>: "<caption>".`.
    Pull out just the caption inside the quotes. Falls back to returning
    the whole string if the format ever changes.
    """
    if not og:
        return None
    m = _OG_CAPTION_RE.search(og)
    if m:
        # Unescape common entities the meta content may have
        return m.group(1).replace('\\"', '"')
    return og


async def detect_own_handle(page: Page) -> str | None:
    """From the authenticated home feed, extract the user's own handle
    from the sidebar 'Profile' link (the only <a> whose inner text is
    exactly 'Profile')."""
    handle = await page.evaluate(
        """
        () => {
          const anchors = Array.from(document.querySelectorAll('a[role="link"]'));
          for (const a of anchors) {
            const text = (a.textContent || '').trim();
            if (text === 'Profile') {
              const href = a.getAttribute('href') || '';
              const m = href.match(/^\\/([^/]+)\\/$/);
              if (m) return m[1];
            }
          }
          return null;
        }
        """
    )
    return handle


async def first_post_href(page: Page, handle: str, *, timeout_ms: int = 15_000) -> str | None:
    """Navigate to /<handle>/ and return the href of the first post
    thumbnail, or None if the grid is empty or didn't render in time."""
    await page.goto(f"https://www.instagram.com/{handle}/", wait_until="domcontentloaded")
    grid_link = page.locator('a[href*="/p/"], a[href*="/reel/"]').first
    try:
        await grid_link.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        return None
    return await grid_link.get_attribute("href")


async def fetch_post_caption(page: Page, shortcode: str) -> str | None:
    """Navigate to /p/<shortcode>/ and pull the caption from og:description."""
    await page.goto(
        f"https://www.instagram.com/p/{shortcode}/",
        wait_until="domcontentloaded",
    )
    og = await page.evaluate(
        """
        () => {
          const m = document.querySelector('meta[property="og:description"]') ||
                    document.querySelector('meta[name="description"]');
          return m ? m.getAttribute('content') : null;
        }
        """
    )
    return extract_caption_from_og(og)
