"""auto-ig CLI entrypoint."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .auth.cookie_import import convert_cookie_editor_json
from .auth.login import run_login
from .auth.session import ChallengeRequiredError, NotAuthenticatedError
from .config import Settings, load_account_config
from .content.loader import discover_posts, load_post
from .publisher.base import PublishResult
from .publisher.playwright_web import PlaywrightWebPublisher
from .queue.pacer import can_publish_now
from .queue.store import JobStatus, QueueStore
from .utils.logging import get_logger, setup_logging

app = typer.Typer(help="Open-source Instagram publisher (Playwright + imported cookies).")
console = Console()
log = get_logger("auto_instagram")


AccountOpt = Annotated[
    str | None,
    typer.Option("--account", "-a", help="Account name (matches config/<name>.yaml)"),
]


def _settings(account: str | None) -> tuple[Settings, str]:
    s = Settings()
    name = account or s.account
    setup_logging(s.log_level)
    return s, name


@app.command()
def login(account: AccountOpt = None) -> None:
    """Open a browser window and log in manually; save the session to disk."""
    s, name = _settings(account)
    cfg = load_account_config(s.account_config_file(name))
    session_file = s.session_file(name)
    console.print(f"[bold]Logging in as:[/bold] {cfg.handle}  (session → {session_file})")
    asyncio.run(run_login(cfg, session_file))


@app.command("import-cookies")
def import_cookies(
    source: Annotated[Path, typer.Argument(help="Cookie-Editor JSON export path")],
    account: AccountOpt = None,
) -> None:
    """Convert a Cookie-Editor JSON export to a Playwright session."""
    s, name = _settings(account)
    _ = load_account_config(s.account_config_file(name))  # validate config exists
    session_file = s.session_file(name)
    summary = convert_cookie_editor_json(source, session_file)
    console.print(
        f"[green]Session saved to {session_file}[/green]\n"
        f"cookies: {summary['cookies_written']}  "
        f"missing_recommended: {summary['missing_recommended'] or 'none'}"
    )


@app.command()
def doctor(account: AccountOpt = None) -> None:
    """Verify the saved session is still logged in."""
    s, name = _settings(account)
    cfg = load_account_config(s.account_config_file(name))
    session_file = s.session_file(name)
    if not session_file.exists():
        console.print(f"[red]No session at {session_file}[/red]. Run `auto-ig login` first.")
        raise typer.Exit(code=2)

    pub = PlaywrightWebPublisher(cfg, session_file)
    ok = asyncio.run(pub.healthcheck())
    if ok:
        console.print(f"[green]OK[/green]: {cfg.handle} session is valid.")
    else:
        console.print(
            f"[red]NOT AUTHENTICATED[/red]: session at {session_file} does not resolve to a logged-in feed."
        )
        raise typer.Exit(code=1)


@app.command()
def publish(
    post_dir: Annotated[Path, typer.Argument(help="Directory containing post.yaml")],
    account: AccountOpt = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Walk the UI but don't click Share")] = False,
) -> None:
    """Publish a single post immediately."""
    s, name = _settings(account)
    cfg = load_account_config(s.account_config_file(name))
    post = load_post(post_dir)

    store = QueueStore(s.queue_db)
    can, reason = can_publish_now(cfg.pacing, store.recent_success_timestamps(name))
    if not can and not dry_run:
        console.print(f"[red]Rate cap hit:[/red] {reason}")
        raise typer.Exit(code=3)

    job_id = store.enqueue(name, post.source_dir)
    store.mark_running(job_id)

    pub = PlaywrightWebPublisher(cfg, s.session_file(name))
    try:
        result: PublishResult = asyncio.run(pub.publish(post, dry_run=dry_run))
    except ChallengeRequiredError as e:
        store.mark_paused(job_id, str(e))
        console.print(f"[yellow]Paused:[/yellow] {e}")
        raise typer.Exit(code=4) from None
    except NotAuthenticatedError as e:
        store.mark_paused(job_id, str(e))
        console.print(f"[red]Not authenticated:[/red] {e}")
        raise typer.Exit(code=4) from None
    except Exception as e:
        store.mark_failed(job_id, repr(e))
        console.print(f"[red]Publish failed:[/red] {e}")
        raise typer.Exit(code=1) from None

    if result.dry_run:
        store.mark_failed(job_id, "dry-run")  # not a real success
        console.print(f"[blue]Dry-run complete[/blue] for {post.source_dir.name}")
        return

    store.mark_succeeded(job_id, shortcode=result.shortcode, url=result.url)
    if result.url:
        console.print(f"[green]Published[/green]: {result.url}")
    else:
        console.print(f"[green]Published[/green] (shortcode unknown) post: {post.source_dir.name}")


@app.command()
def queue(
    account: AccountOpt = None,
    scan: Annotated[bool, typer.Option("--scan/--no-scan", help="Scan content dir and enqueue any post.yaml with a future schedule")] = True,
) -> None:
    """Run due jobs once (designed to be invoked from cron)."""
    s, name = _settings(account)
    cfg = load_account_config(s.account_config_file(name))
    store = QueueStore(s.queue_db)

    if scan:
        for d in discover_posts(s.content_dir):
            try:
                p = load_post(d)
            except Exception as e:
                log.warning("Skipping %s: %s", d, e)
                continue
            store.enqueue(name, p.source_dir, scheduled_at=p.schedule)

    due = store.due_jobs(account=name)
    if not due:
        console.print("[dim]No due jobs.[/dim]")
        return

    pub = PlaywrightWebPublisher(cfg, s.session_file(name))
    for row in due:
        can, reason = can_publish_now(cfg.pacing, store.recent_success_timestamps(name))
        if not can:
            console.print(f"[yellow]Skipping remaining: {reason}[/yellow]")
            break
        job_id = int(row["id"])
        post_dir = Path(row["post_dir"])
        try:
            post = load_post(post_dir)
        except Exception as e:
            store.mark_failed(job_id, f"load_post: {e}")
            continue
        store.mark_running(job_id)
        try:
            result = asyncio.run(pub.publish(post))
        except ChallengeRequiredError as e:
            store.mark_paused(job_id, str(e))
            console.print(f"[yellow]Paused on job {job_id}:[/yellow] {e}")
            break
        except Exception as e:
            store.mark_failed(job_id, repr(e))
            console.print(f"[red]Job {job_id} failed:[/red] {e}")
            continue
        store.mark_succeeded(job_id, shortcode=result.shortcode, url=result.url)
        console.print(f"[green]Published job {job_id}[/green]: {result.url or '(no shortcode)'}")


@app.command("list")
def list_jobs(account: AccountOpt = None) -> None:
    """Show the job queue."""
    s, name = _settings(account)
    store = QueueStore(s.queue_db)
    rows = store.list_all(account=name)
    if not rows:
        console.print("[dim]Queue is empty.[/dim]")
        return
    t = Table(show_header=True, header_style="bold")
    for col in ("id", "status", "post_dir", "scheduled_at", "attempt_count", "shortcode"):
        t.add_column(col)
    for r in rows:
        t.add_row(
            str(r["id"]),
            _colorize_status(r["status"]),
            str(r["post_dir"]),
            r["scheduled_at"] or "-",
            str(r["attempt_count"]),
            r["shortcode"] or "-",
        )
    console.print(t)


def _colorize_status(s: str) -> str:
    color = {
        JobStatus.QUEUED.value: "cyan",
        JobStatus.RUNNING.value: "yellow",
        JobStatus.SUCCEEDED.value: "green",
        JobStatus.FAILED.value: "red",
        JobStatus.PAUSED.value: "magenta",
    }.get(s, "white")
    return f"[{color}]{s}[/{color}]"


if __name__ == "__main__":  # pragma: no cover
    app()
