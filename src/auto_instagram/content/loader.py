"""Load post.yaml descriptors into validated Post objects."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Post

POST_FILENAME = "post.yaml"


def load_post(post_dir: Path) -> Post:
    """Load and validate a post descriptor from `<post_dir>/post.yaml`.

    Media paths in the YAML are resolved relative to post_dir.
    """
    post_dir = post_dir.resolve()
    descriptor = post_dir / POST_FILENAME
    if not descriptor.exists():
        raise FileNotFoundError(f"No {POST_FILENAME} found in {post_dir}")

    raw: dict[str, Any] = yaml.safe_load(descriptor.read_text()) or {}

    media_raw = raw.get("media", [])
    if not isinstance(media_raw, list):
        raise ValueError(f"{descriptor}: 'media' must be a list of paths")
    raw["media"] = [(post_dir / m).resolve() for m in media_raw]
    raw["source_dir"] = post_dir

    return Post.model_validate(raw)


def discover_posts(content_dir: Path) -> list[Path]:
    """Return directories under content_dir that contain a post.yaml."""
    content_dir = content_dir.resolve()
    if not content_dir.exists():
        return []
    return sorted(p.parent for p in content_dir.rglob(POST_FILENAME))
