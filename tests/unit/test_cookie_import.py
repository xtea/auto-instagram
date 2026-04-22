from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_instagram.auth.cookie_import import convert_cookie_editor_json


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
