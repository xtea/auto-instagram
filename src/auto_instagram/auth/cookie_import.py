"""Convert a browser-exported cookie file into Playwright's `storage_state`
format so a real-browser login can be reused.

Two input formats are auto-detected:

1. **Cookie-Editor / EditThisCookie JSON** — a top-level JSON array of cookie
   objects with keys like `name`, `value`, `domain`, `sameSite`,
   `expirationDate`.
2. **Netscape `cookies.txt`** — the `curl`-style format emitted by the
   "Get cookies.txt LOCALLY" Chrome extension and many others. Tab-separated
   rows: `domain  include_subdomains  path  secure  expires  name  value`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger

log = get_logger(__name__)

REQUIRED_COOKIES = {"sessionid", "csrftoken", "ds_user_id"}
RECOMMENDED_COOKIES = {"mid", "ig_did", "rur", "ig_cb", "datr"}

# HttpOnly markers used by different Netscape exporters.
_NETSCAPE_HTTPONLY_PREFIX = "#HttpOnly_"


def convert_cookies_to_storage_state(
    source_path: Path,
    destination_storage_state: Path,
) -> dict[str, Any]:
    """Auto-detect the source format and convert to Playwright storage_state.

    Returns a summary dict: {format, cookies_written, missing_required,
    missing_recommended}.
    """
    text = source_path.read_text()
    if _looks_like_json(text):
        cookies, fmt = _parse_cookie_editor_json(text, source_path), "cookie-editor-json"
    else:
        cookies, fmt = _parse_netscape(text), "netscape"

    ig_cookies = [c for c in cookies if "instagram.com" in c["domain"]]

    seen_names = {c["name"] for c in ig_cookies}
    missing_required = REQUIRED_COOKIES - seen_names
    missing_recommended = RECOMMENDED_COOKIES - seen_names
    if missing_required:
        raise ValueError(
            f"Cookie export is missing required Instagram cookies: "
            f"{sorted(missing_required)}. Re-export from a logged-in browser."
        )

    storage_state = {"cookies": ig_cookies, "origins": []}
    destination_storage_state.parent.mkdir(parents=True, exist_ok=True)
    destination_storage_state.write_text(json.dumps(storage_state, indent=2))

    summary = {
        "format": fmt,
        "cookies_written": len(ig_cookies),
        "total_parsed": len(cookies),
        "missing_required": sorted(missing_required),
        "missing_recommended": sorted(missing_recommended),
    }
    log.info(
        "Wrote %d Instagram cookies to %s (format=%s, total parsed=%d, missing recommended: %s)",
        summary["cookies_written"],
        destination_storage_state,
        summary["format"],
        summary["total_parsed"],
        summary["missing_recommended"] or "none",
    )
    return summary


def convert_cookie_editor_json(
    source_json_path: Path,
    destination_storage_state: Path,
) -> dict[str, Any]:
    """Backwards-compatible wrapper that forces the JSON parser."""
    return convert_cookies_to_storage_state(source_json_path, destination_storage_state)


# ---------- helpers ----------


def _looks_like_json(text: str) -> bool:
    for ch in text.lstrip()[:1]:
        return ch in "[{"
    return False


def _parse_cookie_editor_json(text: str, path: Path) -> list[dict[str, Any]]:
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(
            f"{path} is not a Cookie-Editor JSON export "
            "(expected a top-level list of cookie objects)."
        )
    out: list[dict[str, Any]] = []
    for c in data:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            continue
        domain = c.get("domain") or ""
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
        out.append(cookie)
    return out


def _parse_netscape(text: str) -> list[dict[str, Any]]:
    """Parse Netscape `cookies.txt` format.

    Each data row is tab-separated:
        domain  include_subdomains  path  secure  expires  name  value
    A leading `#HttpOnly_` prefix on `domain` marks the cookie as HttpOnly.
    Lines starting with `#` (other than `#HttpOnly_`) and blank lines are
    comments.
    """
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.rstrip("\r\n")
        if not line or (line.startswith("#") and not line.startswith(_NETSCAPE_HTTPONLY_PREFIX)):
            continue
        http_only = False
        if line.startswith(_NETSCAPE_HTTPONLY_PREFIX):
            line = line[len(_NETSCAPE_HTTPONLY_PREFIX):]
            http_only = True
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _subdomains, path, secure, expires, name, value = parts[:7]
        if not name:
            continue
        cookie: dict[str, Any] = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path or "/",
            "secure": secure.upper() == "TRUE",
            "httpOnly": http_only,
            # Netscape format has no SameSite field; default Lax is Playwright-safe.
            "sameSite": "Lax",
        }
        try:
            exp_i = int(expires)
            if exp_i > 0:
                cookie["expires"] = float(exp_i)
        except ValueError:
            pass
        out.append(cookie)
    return out


def _same_site(raw: str | None) -> str:
    if raw is None:
        return "Lax"
    v = raw.strip().lower()
    if v in {"no_restriction", "unspecified", "none"}:
        return "None"
    if v == "strict":
        return "Strict"
    return "Lax"
