from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from auto_instagram.content.loader import discover_posts, load_post
from auto_instagram.content.models import PostType


def _write_post(tmp_path: Path, *, body: dict, media_files: list[tuple[str, bytes]]) -> Path:
    post_dir = tmp_path / "my-post"
    media_dir = post_dir / "media"
    media_dir.mkdir(parents=True)
    for name, content in media_files:
        (media_dir / name).write_bytes(content)
    (post_dir / "post.yaml").write_text(yaml.safe_dump(body))
    return post_dir


def test_load_feed_post(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "feed", "caption": "hi #x", "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    post = load_post(post_dir)
    assert post.type == PostType.FEED
    assert post.caption == "hi #x"
    assert len(post.media) == 1
    assert post.media[0].exists()


def test_feed_rejects_multiple_media(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "feed", "media": ["./media/a.jpg", "./media/b.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff"), ("b.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match="exactly 1"):
        load_post(post_dir)


def test_carousel_bounds(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "carousel", "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match=r"Carousel must have"):
        load_post(post_dir)


def test_carousel_ok_with_two_items(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={
            "type": "carousel",
            "media": ["./media/a.jpg", "./media/b.jpg"],
        },
        media_files=[("a.jpg", b"\xff\xd8\xff"), ("b.jpg", b"\xff\xd8\xff")],
    )
    post = load_post(post_dir)
    assert post.type == PostType.CAROUSEL
    assert len(post.media) == 2


def test_reel_requires_video(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "reel", "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match="Reel must be a video"):
        load_post(post_dir)


def test_caption_max_chars(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "feed", "caption": "x" * 2201, "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match="Caption"):
        load_post(post_dir)


def test_caption_max_hashtags(tmp_path: Path) -> None:
    caption = " ".join(f"#tag{i}" for i in range(31))
    post_dir = _write_post(
        tmp_path,
        body={"type": "feed", "caption": caption, "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match="hashtag"):
        load_post(post_dir)


def test_discover_posts(tmp_path: Path) -> None:
    _write_post(
        tmp_path,
        body={"type": "feed", "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    (tmp_path / "nested").mkdir()
    _write_post(
        tmp_path / "nested",
        body={"type": "feed", "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    found = discover_posts(tmp_path)
    assert len(found) == 2


def test_missing_media_fails(tmp_path: Path) -> None:
    post_dir = tmp_path / "my-post"
    post_dir.mkdir()
    (post_dir / "post.yaml").write_text(
        yaml.safe_dump({"type": "feed", "media": ["./media/missing.jpg"]})
    )
    with pytest.raises(Exception, match="does not exist"):
        load_post(post_dir)
