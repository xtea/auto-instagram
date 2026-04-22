"""Implementation of `auto-ig init`: scaffold a working directory from
the packaged templates and install Patchright Chrome."""
from __future__ import annotations

import subprocess
import sys
from importlib import resources
from pathlib import Path

from rich.console import Console

console = Console()

TEMPLATES_PKG = "auto_instagram.templates"


def run_init(account: str, *, skip_chrome: bool, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "config").mkdir(exist_ok=True)
    (target_dir / "content").mkdir(exist_ok=True)
    (target_dir / "sessions").mkdir(exist_ok=True)

    _maybe_install_chrome(skip=skip_chrome)
    _scaffold_account_config(target_dir, account)
    _scaffold_example_post(target_dir)
    _scaffold_gitignore(target_dir)
    _print_next_steps(target_dir, account)


def _maybe_install_chrome(*, skip: bool) -> None:
    if skip:
        console.print("[dim]- Skipped Patchright Chrome install (--skip-chrome)[/dim]")
        return
    console.print("[bold]- Installing Patchright Chrome...[/bold]")
    try:
        subprocess.run(
            [sys.executable, "-m", "patchright", "install", "chrome"],
            check=True,
        )
        console.print("  [green]done[/green]")
    except subprocess.CalledProcessError as e:
        console.print(
            f"  [red]Chrome install failed (exit {e.returncode}).[/red] "
            "Run `patchright install chrome` manually to finish setup."
        )


def _scaffold_account_config(target_dir: Path, account: str) -> None:
    dst = target_dir / "config" / f"{account}.yaml"
    if dst.exists():
        console.print(f"[dim]- config/{account}.yaml already exists; not overwriting[/dim]")
        return
    src_text = resources.files(TEMPLATES_PKG).joinpath("account.example.yaml").read_text()
    # Replace the placeholder handle with the account name for a sensible default
    src_text = src_text.replace("handle: your_instagram_handle", f"handle: {account}")
    dst.write_text(src_text)
    console.print(f"[green]- wrote config/{account}.yaml[/green]")


def _scaffold_example_post(target_dir: Path) -> None:
    post_dir = target_dir / "content" / "example-post"
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "media").mkdir(exist_ok=True)

    post_yaml = post_dir / "post.yaml"
    readme = post_dir / "README.md"

    pkg = resources.files(TEMPLATES_PKG).joinpath("example-post")
    if not post_yaml.exists():
        post_yaml.write_text(pkg.joinpath("post.yaml").read_text())
        console.print("[green]- wrote content/example-post/post.yaml[/green]")
    else:
        console.print("[dim]- content/example-post/post.yaml already exists; not overwriting[/dim]")
    if not readme.exists():
        readme.write_text(pkg.joinpath("README.md").read_text())


def _scaffold_gitignore(target_dir: Path) -> None:
    gi = target_dir / ".gitignore"
    entries = [
        "sessions/",
        "*.db",
        "*.db-journal",
        "content/*/media/",
        ".env",
    ]
    existing = gi.read_text().splitlines() if gi.exists() else []
    missing = [e for e in entries if e not in existing]
    if not missing:
        return
    with gi.open("a") as f:
        if existing and not existing[-1].endswith("\n"):
            f.write("\n")
        f.write("\n# auto-instagram\n")
        for e in missing:
            f.write(f"{e}\n")
    console.print(f"[green]- updated .gitignore (+{len(missing)} entries)[/green]")


def _print_next_steps(target_dir: Path, account: str) -> None:
    rel = _try_relative(target_dir)
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print(
        f"  1. Review [cyan]{rel}/config/{account}.yaml[/cyan] — "
        "set handle, timezone, pacing caps."
    )
    console.print(
        f"  2. Authenticate: [cyan]auto-ig login --account {account}[/cyan]\n"
        "     or import cookies: "
        f"[cyan]auto-ig import-cookies ./cookies.txt --account {account}[/cyan]"
    )
    console.print(
        f"  3. Verify:  [cyan]auto-ig doctor --account {account}[/cyan]"
    )
    console.print(
        f"  4. Drop media into [cyan]{rel}/content/example-post/media/[/cyan], "
        "then:"
    )
    console.print(
        f"     [cyan]auto-ig publish {rel}/content/example-post "
        f"--account {account} --dry-run[/cyan]"
    )


def _try_relative(p: Path) -> str:
    try:
        rel = p.resolve().relative_to(Path.cwd())
    except ValueError:
        return str(p)
    s = str(rel)
    return "." if s == "." else f"./{s}"
