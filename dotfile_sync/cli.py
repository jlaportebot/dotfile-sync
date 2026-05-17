"""CLI interface for dotfile-sync using Click."""

from __future__ import annotations

import functools

import click
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .core import DotfileSync, DotfileSyncError, NotInitializedError

console = Console()
err_console = Console(stderr=True)


def _handle_error(func):  # type: ignore[no-untyped-def]
    """Decorator to handle dotfile-sync errors gracefully."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            return func(*args, **kwargs)
        except NotInitializedError as e:
            err_console.print(f"[bold red]Error:[/bold red] {e}")
            raise SystemExit(1) from None
        except DotfileSyncError as e:
            err_console.print(f"[bold red]Error:[/bold red] {e}")
            raise SystemExit(1) from None

    return wrapper


@click.group()
@click.version_option(version=__version__, prog_name="dotfile-sync")
def main() -> None:
    """📁 dotfile-sync — Keep your dotfiles in sync across machines."""
    pass


@main.command()
@click.option("--remote", "-r", default=None, help="Git remote URL for the backup repository.")
@_handle_error
def init(remote: str | None) -> None:
    """Initialize a new dotfile-sync repository."""
    sync = DotfileSync()
    result = sync.init(remote_url=remote)
    console.print(Panel(result, title="✨ Initialized", border_style="green"))


@main.command()
@click.argument("path", type=click.Path())
@_handle_error
def track(path: str) -> None:
    """Add a file or directory to the tracking manifest."""
    sync = DotfileSync()
    result = sync.track(path)
    console.print(f"[green]✓[/green] {result}")


@main.command()
@click.argument("path", type=click.Path())
@_handle_error
def untrack(path: str) -> None:
    """Remove a file or directory from the tracking manifest."""
    sync = DotfileSync()
    result = sync.untrack(path)
    console.print(f"[yellow]✗[/yellow] {result}")


@main.command(name="list")
@_handle_error
def list_files() -> None:
    """Show all tracked files and their sync status."""
    sync = DotfileSync()
    result = sync.list_tracked()
    console.print(result)


@main.command()
@click.option("--message", "-m", default=None, help="Commit message for the backup.")
@_handle_error
def backup(message: str | None) -> None:
    """Copy tracked files into the repo and commit."""
    sync = DotfileSync()
    result = sync.backup(message=message)
    console.print(Panel(result, title="💾 Backup", border_style="blue"))


@main.command()
@click.option("--only", "-o", default=None, help="Restore only a specific file path.")
@_handle_error
def restore(only: str | None) -> None:
    """Copy files from the repo back to their original locations."""
    sync = DotfileSync()
    result = sync.restore(only=only)
    console.print(Panel(result, title="📂 Restore", border_style="green"))


@main.command()
@_handle_error
def diff() -> None:
    """Show differences between live files and the last backup."""
    sync = DotfileSync()
    result = sync.diff()
    console.print(result)


@main.command()
@_handle_error
def status() -> None:
    """Show which tracked files have been modified since last backup."""
    sync = DotfileSync()
    result = sync.status()
    console.print(result)


@main.command()
@_handle_error
def push() -> None:
    """Push the backup repo to its remote."""
    sync = DotfileSync()
    result = sync.push()
    console.print(f"[green]✓[/green] {result}")


@main.command()
@_handle_error
def pull() -> None:
    """Pull changes from the remote and restore."""
    sync = DotfileSync()
    result = sync.pull()
    console.print(f"[green]✓[/green] {result}")


if __name__ == "__main__":
    main()
