"""Publisher protocol — any backend (Playwright web, instagrapi, Graph API)
must conform to this."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..content.models import Post


@dataclass(slots=True)
class PublishResult:
    ok: bool
    shortcode: str | None = None  # IG media shortcode when we can extract it
    url: str | None = None
    error: str | None = None
    dry_run: bool = False


@runtime_checkable
class Publisher(Protocol):
    async def publish(self, post: Post, *, dry_run: bool = False) -> PublishResult: ...

    async def healthcheck(self) -> bool: ...
