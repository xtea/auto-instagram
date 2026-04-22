from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_instagram.auth.cookie_import import (
    convert_cookie_editor_json,
    convert_cookies_to_storage_state,
)


def _cookie(name: str, value: str = "x", **extra: object) -> dict:
    return {
        "name": name,
        "value": value,
        "domain": ".instagram.com",
        "path": "/",
        "secure": True,
        "sameSite": "lax",
        **extra,
    }


def _full_export() -> list[dict]:
    return [
        _cookie("sessionid", "abc"),
        _cookie("csrftoken", "xyz"),
        _cookie("ds_user_id", "1234"),
        _cookie("mid"),
        _cookie("ig_did"),
        _cookie("rur"),
        _cookie("ig_cb"),
        _cookie("datr"),
    ]


def test_converts_full_export(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(json.dumps(_full_export()))
    dst = tmp_path / "storage.json"
    summary = convert_cookie_editor_json(src, dst)
    assert summary["cookies_written"] == 8
    assert summary["missing_required"] == []
    assert summary["missing_recommended"] == []
    data = json.loads(dst.read_text())
    assert {c["name"] for c in data["cookies"]} == {c["name"] for c in _full_export()}


def test_rejects_missing_required(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(json.dumps([_cookie("sessionid"), _cookie("csrftoken")]))
    dst = tmp_path / "storage.json"
    with pytest.raises(ValueError, match="missing required"):
        convert_cookie_editor_json(src, dst)


def test_reports_missing_recommended(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(
        json.dumps([
            _cookie("sessionid"),
            _cookie("csrftoken"),
            _cookie("ds_user_id"),
        ])
    )
    dst = tmp_path / "storage.json"
    summary = convert_cookie_editor_json(src, dst)
    assert summary["missing_recommended"] == sorted(
        ["mid", "ig_did", "rur", "ig_cb", "datr"]
    )


def test_filters_other_domains(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(
        json.dumps([
            *_full_export(),
            {
                "name": "tracker",
                "value": "y",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
                "sameSite": "lax",
            },
        ])
    )
    dst = tmp_path / "storage.json"
    summary = convert_cookie_editor_json(src, dst)
    assert summary["cookies_written"] == 8
    data = json.loads(dst.read_text())
    assert all("instagram.com" in c["domain"] for c in data["cookies"])


def test_rejects_non_list(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(json.dumps({"not": "a list"}))
    dst = tmp_path / "storage.json"
    with pytest.raises(ValueError, match="not a Cookie-Editor"):
        convert_cookie_editor_json(src, dst)


def test_samesite_normalization(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    raw = _full_export()
    raw[0]["sameSite"] = "no_restriction"
    raw[1]["sameSite"] = "strict"
    src.write_text(json.dumps(raw))
    dst = tmp_path / "storage.json"
    convert_cookie_editor_json(src, dst)
    data = json.loads(dst.read_text())
    sess = next(c for c in data["cookies"] if c["name"] == "sessionid")
    csrf = next(c for c in data["cookies"] if c["name"] == "csrftoken")
    assert sess["sameSite"] == "None"
    assert csrf["sameSite"] == "Strict"


# ---- Netscape cookies.txt format ----


def _netscape_row(
    domain: str, name: str, value: str, *, http_only: bool = False, secure: bool = True
) -> str:
    line = "\t".join([
        domain,
        "TRUE",
        "/",
        "TRUE" if secure else "FALSE",
        "1999999999",
        name,
        value,
    ])
    return f"#HttpOnly_{line}" if http_only else line


def _netscape_full() -> str:
    rows = [
        "# Netscape HTTP Cookie File",
        "# comment",
        "",
        _netscape_row(".instagram.com", "sessionid", "abc", http_only=True),
        _netscape_row(".instagram.com", "csrftoken", "xyz"),
        _netscape_row(".instagram.com", "ds_user_id", "1234"),
        _netscape_row(".instagram.com", "mid", "m"),
        _netscape_row(".instagram.com", "ig_did", "d"),
        _netscape_row(".instagram.com", "rur", "r"),
        _netscape_row(".instagram.com", "ig_cb", "b"),
        _netscape_row(".instagram.com", "datr", "t"),
        _netscape_row(".example.com", "other", "ignored"),
    ]
    return "\n".join(rows) + "\n"


def test_netscape_auto_detect(tmp_path: Path) -> None:
    src = tmp_path / "cookies.txt"
    src.write_text(_netscape_full())
    dst = tmp_path / "storage.json"
    summary = convert_cookies_to_storage_state(src, dst)
    assert summary["format"] == "netscape"
    assert summary["cookies_written"] == 8
    assert summary["total_parsed"] >= 9  # includes the example.com row
    assert summary["missing_required"] == []
    assert summary["missing_recommended"] == []
    data = json.loads(dst.read_text())
    assert all("instagram.com" in c["domain"] for c in data["cookies"])
    sess = next(c for c in data["cookies"] if c["name"] == "sessionid")
    assert sess["httpOnly"] is True
    assert sess["value"] == "abc"


def test_netscape_rejects_missing_required(tmp_path: Path) -> None:
    rows = [
        "# Netscape HTTP Cookie File",
        _netscape_row(".instagram.com", "sessionid", "abc"),
        _netscape_row(".instagram.com", "csrftoken", "xyz"),
    ]
    src = tmp_path / "cookies.txt"
    src.write_text("\n".join(rows) + "\n")
    dst = tmp_path / "storage.json"
    with pytest.raises(ValueError, match="missing required"):
        convert_cookies_to_storage_state(src, dst)


def test_netscape_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    src = tmp_path / "cookies.txt"
    src.write_text(_netscape_full())
    dst = tmp_path / "storage.json"
    convert_cookies_to_storage_state(src, dst)
    data = json.loads(dst.read_text())
    assert all(c["name"] for c in data["cookies"])


def test_auto_detect_routes_json(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(json.dumps(_full_export()))
    dst = tmp_path / "storage.json"
    summary = convert_cookies_to_storage_state(src, dst)
    assert summary["format"] == "cookie-editor-json"
