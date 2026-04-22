"""Convert a Cookie-Editor / EditThisCookie JSON export into Playwright's
`storage_state` format so we can reuse cookies captured in a real browser."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger

log = get_logger(__name__)

# Instagram cookies that must be present for an authenticated session (2026).
REQUIRED_COOKIES = {"sessionid", "csrftoken", "ds_user_id"}
# Nice-to-have cookies that reduce challenge risk when preserved.
RECOMMENDED_COOKIES = {"mid", "ig_did", "rur", "ig_cb", "datr"}


def _same_site(raw: str | None) -> str:
    """Normalize SameSite from browser-extension formats to Playwright's enum."""
    if raw is None:
        return "Lax"
    v = raw.strip().lower()
    if v in {"no_restriction", "unspecified", "none"}:
        return "None"
    if v == "strict":
        return "Strict"
    return "Lax"


def convert_cookie_editor_json(
    source_json_path: Path,
    destination_storage_state: Path,
) -> dict[str, Any]:
    """Read a Cookie-Editor export file and write a Playwright storage_state JSON.

    Returns a summary dict: {cookies_written, missing_required, missing_recommended}.
    """
    data = json.loads(source_json_path.read_text())
    if not isinstance(data, list):
        raise ValueError(
            f"{source_json_path} is not a Cookie-Editor JSON export "
            "(expected a top-level list of cookie objects)."
        )

    playwright_cookies: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for c in data:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            continue
        domain = c.get("domain") or ".instagram.com"
        # Skip cookies from other domains if present in the export.
        if "instagram.com" not in domain:
            continue

        cookie: dict[str, Any] = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": c.get("path") or "/",
            "secure": bool(c.get("secure", True)),
            "httpOnly": bool(c.get("httpOnly", False)),
            "sameSite": _same_site(c.get("sameSite")),
        }
        if (exp := c.get("expirationDate")) is not None:
            cookie["expires"] = float(exp)
        playwright_cookies.append(cookie)
        seen_names.add(name)

    missing_required = REQUIRED_COOKIES - seen_names
    missing_recommended = RECOMMENDED_COOKIES - seen_names

    if missing_required:
        raise ValueError(
            f"Cookie export is missing required Instagram cookies: "
            f"{sorted(missing_required)}. Re-export from a logged-in browser."
        )

    storage_state = {"cookies": playwright_cookies, "origins": []}
    destination_storage_state.parent.mkdir(parents=True, exist_ok=True)
    destination_storage_state.write_text(json.dumps(storage_state, indent=2))

    summary = {
        "cookies_written": len(playwright_cookies),
        "missing_required": sorted(missing_required),
        "missing_recommended": sorted(missing_recommended),
    }
    log.info(
        "Wrote %d cookies to %s (missing recommended: %s)",
        summary["cookies_written"],
        destination_storage_state,
        summary["missing_recommended"] or "none",
    )
    return summary
