"""Content descriptor models: Post, media kinds, IG limits."""
from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator


class PostType(StrEnum):
    FEED = "feed"
    CAROUSEL = "carousel"
    REEL = "reel"


# Instagram hard limits (current as of April 2026)
CAPTION_MAX_CHARS = 2200
HASHTAG_MAX_COUNT = 30
CAROUSEL_MAX_ITEMS = 20
CAROUSEL_MIN_ITEMS = 2
REEL_MAX_SECONDS = 90

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}


class UserTag(BaseModel):
    handle: str
    x: float | None = None  # 0..1 normalized coords on the image, optional
    y: float | None = None


class Post(BaseModel):
    """Loaded post descriptor. Paths are absolute after loading."""

    type: PostType
    caption: str = ""
    media: list[Path] = Field(min_length=1)
    schedule: datetime | None = None
    user_tags: list[UserTag] = Field(default_factory=list)
    location: str | None = None
    source_dir: Path  # where post.yaml lives, for logging

    @field_validator("caption")
    @classmethod
    def _caption_limits(cls, v: str) -> str:
        if len(v) > CAPTION_MAX_CHARS:
            raise ValueError(
                f"Caption is {len(v)} chars; Instagram caps captions at {CAPTION_MAX_CHARS}."
            )
        hashtags = re.findall(r"#[\w一-鿿]+", v)
        if len(hashtags) > HASHTAG_MAX_COUNT:
            raise ValueError(
                f"Caption has {len(hashtags)} hashtags; Instagram caps at {HASHTAG_MAX_COUNT}."
            )
        return v

    @model_validator(mode="after")
    def _validate_media_for_type(self) -> Self:
        for p in self.media:
            if not p.exists():
                raise ValueError(f"Media file does not exist: {p}")
            if not p.is_file():
                raise ValueError(f"Media path is not a file: {p}")

        if self.type == PostType.FEED:
            if len(self.media) != 1:
                raise ValueError(
                    f"Feed posts must have exactly 1 media file; got {len(self.media)}. "
                    "Use type: carousel for multiple items."
                )
            if self.media[0].suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                raise ValueError(f"Unsupported media extension: {self.media[0].suffix}")

        elif self.type == PostType.CAROUSEL:
            if not (CAROUSEL_MIN_ITEMS <= len(self.media) <= CAROUSEL_MAX_ITEMS):
                raise ValueError(
                    f"Carousel must have {CAROUSEL_MIN_ITEMS}..{CAROUSEL_MAX_ITEMS} items; "
                    f"got {len(self.media)}."
                )
            for p in self.media:
                if p.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                    raise ValueError(f"Unsupported carousel item extension: {p.suffix}")

        elif self.type == PostType.REEL:
            if len(self.media) != 1:
                raise ValueError(f"Reels must have exactly 1 video; got {len(self.media)}.")
            if self.media[0].suffix.lower() not in VIDEO_EXTENSIONS:
                raise ValueError(
                    f"Reel must be a video file; got {self.media[0].suffix}. "
                    f"Accepted: {sorted(VIDEO_EXTENSIONS)}"
                )

        return self
