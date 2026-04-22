"""SQLite-backed job store for the publish queue."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL,
    post_dir TEXT NOT NULL,
    status TEXT NOT NULL,
    scheduled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    shortcode TEXT,
    url TEXT,
    UNIQUE (account, post_dir)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_account ON jobs (status, account);
CREATE INDEX IF NOT EXISTS idx_jobs_scheduled_at ON jobs (scheduled_at);
"""


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PAUSED = "paused"


class QueueStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def enqueue(
        self,
        account: str,
        post_dir: Path,
        *,
        scheduled_at: datetime | None = None,
    ) -> int:
        now = _utc_iso()
        with self._conn() as c:
            cur = c.execute(
                """
                INSERT OR REPLACE INTO jobs
                  (account, post_dir, status, scheduled_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    account,
                    str(post_dir),
                    JobStatus.QUEUED.value,
                    scheduled_at.astimezone(UTC).isoformat() if scheduled_at else None,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid or 0)

    def mark_running(self, job_id: int) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE jobs SET status=?, updated_at=?, attempt_count=attempt_count+1 WHERE id=?",
                (JobStatus.RUNNING.value, _utc_iso(), job_id),
            )

    def mark_succeeded(self, job_id: int, *, shortcode: str | None, url: str | None) -> None:
        with self._conn() as c:
            c.execute(
                """
                UPDATE jobs
                SET status=?, updated_at=?, shortcode=?, url=?, last_error=NULL
                WHERE id=?
                """,
                (JobStatus.SUCCEEDED.value, _utc_iso(), shortcode, url, job_id),
            )

    def mark_failed(self, job_id: int, error: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE jobs SET status=?, updated_at=?, last_error=? WHERE id=?",
                (JobStatus.FAILED.value, _utc_iso(), error, job_id),
            )

    def mark_paused(self, job_id: int, reason: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE jobs SET status=?, updated_at=?, last_error=? WHERE id=?",
                (JobStatus.PAUSED.value, _utc_iso(), reason, job_id),
            )

    def due_jobs(self, account: str | None = None, *, now: datetime | None = None) -> list[sqlite3.Row]:
        now = now or datetime.now(UTC)
        with self._conn() as c:
            if account:
                cur = c.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status=? AND account=?
                      AND (scheduled_at IS NULL OR scheduled_at<=?)
                    ORDER BY COALESCE(scheduled_at, created_at) ASC
                    """,
                    (JobStatus.QUEUED.value, account, now.isoformat()),
                )
            else:
                cur = c.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status=?
                      AND (scheduled_at IS NULL OR scheduled_at<=?)
                    ORDER BY COALESCE(scheduled_at, created_at) ASC
                    """,
                    (JobStatus.QUEUED.value, now.isoformat()),
                )
            return list(cur.fetchall())

    def recent_success_timestamps(self, account: str) -> list[datetime]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT updated_at FROM jobs WHERE account=? AND status=?",
                (account, JobStatus.SUCCEEDED.value),
            )
            return [datetime.fromisoformat(r["updated_at"]) for r in cur.fetchall()]

    def list_all(self, *, account: str | None = None) -> list[sqlite3.Row]:
        with self._conn() as c:
            if account:
                cur = c.execute(
                    "SELECT * FROM jobs WHERE account=? ORDER BY id DESC",
                    (account,),
                )
            else:
                cur = c.execute("SELECT * FROM jobs ORDER BY id DESC")
            return list(cur.fetchall())


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()
