from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from auto_instagram.config import PacingSettings
from auto_instagram.queue.pacer import (
    can_publish_now,
    humanized_step_delay,
    posts_in_last_24h,
    pre_run_idle_seconds,
)


def test_step_delay_within_bounds() -> None:
    p = PacingSettings(min_step_delay_seconds=5, max_step_delay_seconds=15)
    rng = random.Random(42)
    for _ in range(100):
        d = humanized_step_delay(p, rng=rng)
        assert 5 <= d <= 15


def test_pre_run_idle_within_bounds() -> None:
    p = PacingSettings(pre_run_idle_seconds_min=10, pre_run_idle_seconds_max=20)
    rng = random.Random(42)
    for _ in range(100):
        d = pre_run_idle_seconds(p, rng=rng)
        assert 10 <= d <= 20


def test_posts_in_last_24h() -> None:
    now = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)
    ts = [
        now - timedelta(hours=1),
        now - timedelta(hours=23, minutes=59),
        now - timedelta(hours=24, minutes=1),
        now - timedelta(days=5),
    ]
    assert posts_in_last_24h(ts, now=now) == 2


def test_posts_in_last_24h_handles_naive_datetimes() -> None:
    now = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)
    naive = datetime(2026, 4, 22, 11, 0)
    assert posts_in_last_24h([naive], now=now) == 1


def test_can_publish_respects_cap() -> None:
    p = PacingSettings(max_posts_per_day=3)
    now = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)
    ok, reason = can_publish_now(p, [now - timedelta(hours=1)] * 3, now=now)
    assert not ok
    assert reason is not None and "daily cap" in reason


def test_can_publish_under_cap() -> None:
    p = PacingSettings(max_posts_per_day=3)
    now = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)
    ok, reason = can_publish_now(p, [now - timedelta(hours=1)] * 2, now=now)
    assert ok
    assert reason is None
