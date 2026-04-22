"""Pacing: enforce per-day post caps and compute humanized delays."""
from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from ..config import PacingSettings


def humanized_step_delay(pacing: PacingSettings, *, rng: random.Random | None = None) -> float:
    r = rng or random
    return r.uniform(pacing.min_step_delay_seconds, pacing.max_step_delay_seconds)


def pre_run_idle_seconds(pacing: PacingSettings, *, rng: random.Random | None = None) -> float:
    r = rng or random
    return r.uniform(pacing.pre_run_idle_seconds_min, pacing.pre_run_idle_seconds_max)


def posts_in_last_24h(timestamps: list[datetime], *, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=24)
    return sum(1 for t in timestamps if _as_utc(t) >= cutoff)


def can_publish_now(
    pacing: PacingSettings,
    recent_timestamps: list[datetime],
    *,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    count = posts_in_last_24h(recent_timestamps, now=now)
    if count >= pacing.max_posts_per_day:
        return False, (
            f"Per-account daily cap reached: {count}/{pacing.max_posts_per_day} "
            "posts in the last 24 hours."
        )
    return True, None


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
