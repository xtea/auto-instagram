from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_instagram.queue.store import JobStatus, QueueStore


def test_enqueue_and_list(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "q.db")
    job_id = store.enqueue("demo", tmp_path / "post-a")
    assert job_id > 0
    all_jobs = store.list_all(account="demo")
    assert len(all_jobs) == 1
    assert all_jobs[0]["status"] == JobStatus.QUEUED.value


def test_upsert_on_reenqueue(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "q.db")
    id1 = store.enqueue("demo", tmp_path / "post-a")
    id2 = store.enqueue("demo", tmp_path / "post-a")
    all_jobs = store.list_all(account="demo")
    assert len(all_jobs) == 1
    assert id2 == id1 or id2 > 0


def test_due_jobs_respects_schedule(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "q.db")
    now = datetime.now(UTC)
    store.enqueue("demo", tmp_path / "future", scheduled_at=now + timedelta(hours=1))
    store.enqueue("demo", tmp_path / "past", scheduled_at=now - timedelta(minutes=5))
    store.enqueue("demo", tmp_path / "unscheduled")
    due = store.due_jobs(account="demo", now=now)
    due_dirs = {row["post_dir"] for row in due}
    assert str(tmp_path / "past") in due_dirs
    assert str(tmp_path / "unscheduled") in due_dirs
    assert str(tmp_path / "future") not in due_dirs


def test_lifecycle(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "q.db")
    job_id = store.enqueue("demo", tmp_path / "p")
    store.mark_running(job_id)
    store.mark_succeeded(job_id, shortcode="ABC123", url="https://i/p/ABC123/")
    rows = store.list_all(account="demo")
    assert rows[0]["status"] == JobStatus.SUCCEEDED.value
    assert rows[0]["shortcode"] == "ABC123"
    assert rows[0]["attempt_count"] == 1


def test_recent_success_timestamps(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "q.db")
    j = store.enqueue("demo", tmp_path / "p")
    store.mark_succeeded(j, shortcode=None, url=None)
    ts = store.recent_success_timestamps("demo")
    assert len(ts) == 1
    assert ts[0].tzinfo is not None


def test_paused_state(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "q.db")
    j = store.enqueue("demo", tmp_path / "p")
    store.mark_paused(j, "challenge_required")
    rows = store.list_all(account="demo")
    assert rows[0]["status"] == JobStatus.PAUSED.value
    assert rows[0]["last_error"] == "challenge_required"
