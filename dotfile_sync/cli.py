"""CLI interface for dotfile-sync using Click."""

from __future__ import annotations

import functools

import click
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .core import DotfileSync, DotfileSyncError, NotInitializedError
from .templates import TemplateEngine

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
@click.option(
    "--template", "-t", is_flag=True, help="Track as a template for variable substitution."
)
@_handle_error
def track(path: str, template: bool) -> None:
    """Add a file or directory to the tracking manifest."""
    sync = DotfileSync()
    result = sync.track(path, as_template=template)
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
@click.option(
    "--dry-run", is_flag=True, help="Preview what would be backed up without making changes."
)
@click.option(
    "--conflict-strategy",
    type=click.Choice(["skip", "keep-local", "keep-repo", "keep-newer", "make-backup", "abort"]),
    default="make-backup",
    help="How to handle sync conflicts.",
)
@_handle_error
def backup(message: str | None, dry_run: bool, conflict_strategy: str) -> None:
    """Copy tracked files into the repo and commit."""
    from .conflicts import ConflictStrategy

    strategy_map = {
        "skip": ConflictStrategy.SKIP,
        "keep-local": ConflictStrategy.KEEP_LOCAL,
        "keep-repo": ConflictStrategy.KEEP_REPO,
        "keep-newer": ConflictStrategy.KEEP_NEWER,
        "make-backup": ConflictStrategy.MAKE_BACKUP,
        "abort": ConflictStrategy.ABORT,
    }
    sync = DotfileSync()
    result = sync.backup(
        message=message,
        dry_run=dry_run,
        conflict_strategy=strategy_map[conflict_strategy],
    )
    console.print(Panel(result, title="💾 Backup", border_style="blue"))


@main.command()
@click.option("--only", "-o", default=None, help="Restore only a specific file path.")
@click.option("--no-render", is_flag=True, help="Skip template rendering, write raw content.")
@click.option(
    "--dry-run", is_flag=True, help="Preview what would be restored without making changes."
)
@click.option(
    "--conflict-strategy",
    type=click.Choice(["skip", "keep-local", "keep-repo", "keep-newer", "make-backup", "abort"]),
    default="make-backup",
    help="How to handle sync conflicts.",
)
@_handle_error
def restore(only: str | None, no_render: bool, dry_run: bool, conflict_strategy: str) -> None:
    """Copy files from the repo back to their original locations."""
    from .conflicts import ConflictStrategy

    strategy_map = {
        "skip": ConflictStrategy.SKIP,
        "keep-local": ConflictStrategy.KEEP_LOCAL,
        "keep-repo": ConflictStrategy.KEEP_REPO,
        "keep-newer": ConflictStrategy.KEEP_NEWER,
        "make-backup": ConflictStrategy.MAKE_BACKUP,
        "abort": ConflictStrategy.ABORT,
    }
    sync = DotfileSync()
    result = sync.restore(
        only=only,
        render=not no_render,
        dry_run=dry_run,
        conflict_strategy=strategy_map[conflict_strategy],
    )
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


# --- Template & Context Commands ---


@main.group()
def template() -> None:
    """Manage template files and contexts."""
    pass


@template.command("scan")
@click.argument("path", type=click.Path())
@_handle_error
def template_scan(path: str) -> None:
    """Scan a file for template variables.

    Shows all Jinja2 variables used in the file without modifying anything.
    """
    from pathlib import Path

    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise DotfileSyncError(f"Path does not exist: {source}")

    try:
        content = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise DotfileSyncError(f"Cannot read {source} as text")

    engine = TemplateEngine()
    if not engine.is_template(content):
        console.print(f"[yellow]No template syntax found in {source}[/yellow]")
        return

    variables = engine.extract_variables(content)
    if variables:
        console.print(f"[bold]Template variables in {source}:[/bold]")
        for var in sorted(variables):
            console.print(f"  • [cyan]{var}[/cyan]")
    else:
        console.print(f"Template syntax found but no variables extracted from {source}")


@template.command("render")
@click.argument("path", type=click.Path())
@click.option(
    "--context",
    "-c",
    multiple=True,
    help="Context key=value pairs (e.g., -c name=john).",
)
@click.option("--dry-run", is_flag=True, help="Print rendered output without writing to disk.")
@_handle_error
def template_render(path: str, context: tuple[str, ...], dry_run: bool) -> None:
    """Render a template file with the active context.

    By default renders using the stored context. Override with --context flags.
    """
    from pathlib import Path

    sync = DotfileSync()
    sync._ensure_initialized()
    source = Path(path).expanduser().resolve()

    if not source.exists():
        raise DotfileSyncError(f"Path does not exist: {source}")

    try:
        content = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise DotfileSyncError(f"Cannot read {source} as text")

    engine = TemplateEngine()

    # Build context
    if context:
        ctx: dict = {}
        for pair in context:
            if "=" not in pair:
                raise DotfileSyncError(f"Invalid context format: {pair}. Use key=value")
            key, value = pair.split("=", 1)
            ctx[key] = value
    else:
        ctx = sync._build_render_context()

    rendered = engine.render(content, ctx)

    if dry_run:
        console.print(Panel(rendered, title=f"Rendered: {source.name}", border_style="blue"))
    else:
        source.write_text(rendered, encoding="utf-8")
        console.print(f"[green]✓[/green] Rendered template to {source}")


# --- Context Management Commands ---


@main.group()
def context() -> None:
    """Manage template contexts (variables per machine/profile)."""
    pass


@context.command("list")
@_handle_error
def context_list() -> None:
    """List all available contexts."""
    sync = DotfileSync()
    sync._ensure_initialized()
    ctx_mgr = sync._get_context_manager()
    contexts = ctx_mgr.list_contexts()

    if not contexts:
        console.print("[yellow]No contexts defined[/yellow]")
        return

    console.print("[bold]Available contexts:[/bold]")
    for name in sorted(contexts):
        ctx = ctx_mgr.get_context(name)
        console.print(f"  • [cyan]{name}[/cyan] ({len(ctx)} variables)")


@context.command("show")
@click.argument("name")
@_handle_error
def context_show(name: str) -> None:
    """Show variables in a specific context."""
    sync = DotfileSync()
    sync._ensure_initialized()
    ctx_mgr = sync._get_context_manager()
    ctx = ctx_mgr.get_context(name)

    if not ctx:
        console.print(f"[yellow]Context '{name}' is empty or does not exist[/yellow]")
        return

    console.print(f"[bold]Context: {name}[/bold]")
    for key, value in sorted(ctx.items()):
        console.print(f"  {key} = [cyan]{value}[/cyan]")


@context.command("set")
@click.argument("name")
@click.argument("key_value", nargs=-1, required=True)
@_handle_error
def context_set(name: str, key_value: tuple[str, ...]) -> None:
    """Set variables in a context. Usage: context set <name> key=value ...

    Example: dotfile-sync context set default hostname=myserver email=me@example.com
    """
    sync = DotfileSync()
    sync._ensure_initialized()
    ctx_mgr = sync._get_context_manager()

    # Merge with existing context
    existing = ctx_mgr.get_context(name)
    for pair in key_value:
        if "=" not in pair:
            raise DotfileSyncError(f"Invalid format: {pair}. Use key=value")
        key, value = pair.split("=", 1)
        existing[key] = value

    ctx_mgr.set_context(name, existing)
    console.print(f"[green]✓[/green] Updated context '{name}' with {len(key_value)} variable(s)")


@context.command("delete")
@click.argument("name")
@click.argument("key", nargs=-1, required=True)
@_handle_error
def context_delete(name: str, key: tuple[str, ...]) -> None:
    """Delete specific keys from a context."""
    sync = DotfileSync()
    sync._ensure_initialized()
    ctx_mgr = sync._get_context_manager()

    existing = ctx_mgr.get_context(name)
    removed = 0
    for k in key:
        if k in existing:
            del existing[k]
            removed += 1

    if removed:
        ctx_mgr.set_context(name, existing)
        console.print(f"[yellow]✗[/yellow] Removed {removed} key(s) from context '{name}'")
    else:
        console.print(f"[yellow]No matching keys found in context '{name}'[/yellow]")


# --- Profile Commands ---


@main.group()
def profile() -> None:
    """Manage profiles for different machines/environments."""
    pass


@profile.command("activate")
@click.argument("name")
@_handle_error
def profile_activate(name: str) -> None:
    """Set the active profile for template rendering."""
    from .core import Manifest

    sync = DotfileSync()
    sync._ensure_initialized()
    manifest = Manifest(sync.manifest_path)
    manifest.active_profile = name
    console.print(f"[green]✓[/green] Active profile set to '{name}'")


@profile.command("deactivate")
@_handle_error
def profile_deactivate() -> None:
    """Clear the active profile."""
    from .core import Manifest

    sync = DotfileSync()
    sync._ensure_initialized()
    manifest = Manifest(sync.manifest_path)
    manifest.active_profile = None
    console.print("[green]✓[/green] Active profile cleared")


@profile.command("machine")
@click.argument("name")
@_handle_error
def profile_machine(name: str) -> None:
    """Set the machine name for template rendering."""
    from .core import Manifest

    sync = DotfileSync()
    sync._ensure_initialized()
    manifest = Manifest(sync.manifest_path)
    manifest.machine_name = name
    console.print(f"[green]✓[/green] Machine name set to '{name}'")


@profile.command("show")
@_handle_error
def profile_show() -> None:
    """Show the current active profile and machine configuration."""
    from .core import Manifest

    sync = DotfileSync()
    sync._ensure_initialized()
    manifest = Manifest(sync.manifest_path)

    console.print("[bold]Current Configuration:[/bold]")
    profile_name = manifest.active_profile or "(none)"
    machine = manifest.machine_name or "(none)"
    console.print(f"  Active profile: [cyan]{profile_name}[/cyan]")
    console.print(f"  Machine name:   [cyan]{machine}[/cyan]")


# --- Hook Commands ---


@main.group()
def hook() -> None:
    """Manage hooks (commands that run before/after sync operations)."""
    pass


@hook.command("list")
@_handle_error
def hook_list() -> None:
    """List all configured hooks."""
    from .hooks import create_hook_config

    sync = DotfileSync()
    sync._ensure_initialized()
    config = create_hook_config(sync.repo_dir)
    all_hooks = config.list_all()

    if not all_hooks:
        console.print("[yellow]No hooks configured[/yellow]")
        return

    console.print("[bold]Configured hooks:[/bold]")
    for event_name, commands in sorted(all_hooks.items()):
        console.print(f"  [cyan]{event_name}[/cyan]:")
        for i, cmd in enumerate(commands, 1):
            console.print(f"    {i}. {cmd}")


@hook.command("set")
@click.argument(
    "event",
    type=click.Choice([
        "pre-backup",
        "post-backup",
        "pre-restore",
        "post-restore",
        "pre-track",
        "post-track",
    ]),
)
@click.argument("command")
@_handle_error
def hook_set(event: str, command: str) -> None:
    """Add a hook command for an event.

    \b
    Events: pre-backup, post-backup, pre-restore, post-restore,
            pre-track, post-track
    """
    from .hooks import HookEvent, create_hook_config

    event_map = {
        "pre-backup": HookEvent.PRE_BACKUP,
        "post-backup": HookEvent.POST_BACKUP,
        "pre-restore": HookEvent.PRE_RESTORE,
        "post-restore": HookEvent.POST_RESTORE,
        "pre-track": HookEvent.PRE_TRACK,
        "post-track": HookEvent.POST_TRACK,
    }

    sync = DotfileSync()
    sync._ensure_initialized()
    config = create_hook_config(sync.repo_dir)
    config.add_hook(event_map[event], command)
    console.print(f"[green]✓[/green] Hook added: {event} → {command}")


@hook.command("remove")
@click.argument(
    "event",
    type=click.Choice([
        "pre-backup",
        "post-backup",
        "pre-restore",
        "post-restore",
        "pre-track",
        "post-track",
    ]),
)
@click.argument("index", type=int)
@_handle_error
def hook_remove(event: str, index: int) -> None:
    """Remove a hook by its index."""
    from .hooks import HookEvent, create_hook_config

    event_map = {
        "pre-backup": HookEvent.PRE_BACKUP,
        "post-backup": HookEvent.POST_BACKUP,
        "pre-restore": HookEvent.PRE_RESTORE,
        "post-restore": HookEvent.POST_RESTORE,
        "pre-track": HookEvent.PRE_TRACK,
        "post-track": HookEvent.POST_TRACK,
    }

    sync = DotfileSync()
    sync._ensure_initialized()
    config = create_hook_config(sync.repo_dir)
    if config.remove_hook(event_map[event], index - 1):  # 1-indexed display
        console.print(f"[yellow]✗[/yellow] Removed hook #{index} from {event}")
    else:
        console.print(f"[yellow]Invalid hook index: {index}[/yellow]")


# --- Ignore Commands ---


@main.group()
def ignore() -> None:
    """Manage ignore patterns (like .gitignore)."""
    pass


@ignore.command("list")
@_handle_error
def ignore_list() -> None:
    """List all active ignore patterns."""
    from .ignore import create_ignore_matcher

    sync = DotfileSync()
    sync._ensure_initialized()
    matcher = create_ignore_matcher(sync.repo_dir)

    console.print(f"[bold]Ignore patterns ({matcher.count()}):[/bold]")
    for i, pattern in enumerate(matcher.patterns, 1):
        if not pattern.raw or pattern.raw.startswith("#"):
            continue
        label = ""
        if pattern.negated:
            label = " [dim](negated)[/dim]"
        elif pattern.directory_only:
            label = " [dim](dir)[/dim]"
        console.print(f"  {i}. [cyan]{pattern.raw}[/cyan]{label}")


@ignore.command("add")
@click.argument("pattern")
@_handle_error
def ignore_add(pattern: str) -> None:
    """Add an ignore pattern. Supports gitignore syntax."""
    sync = DotfileSync()
    sync._ensure_initialized()

    # Append to .dotfileignore file
    ignore_file = sync.repo_dir / ".dotfileignore"
    try:
        with ignore_file.open("a") as f:
            f.write(pattern + "\n")
    except OSError as exc:
        raise DotfileSyncError(f"Failed to write ignore file: {exc}") from exc

    console.print(f"[green]✓[/green] Added ignore pattern: {pattern}")


# --- Dry-Run Commands ---


@main.command("dry-run")
@click.option("--operation", type=click.Choice(["backup", "restore"]), default="backup")
@click.option("--only", "-o", default=None, help="Only check this specific file.")
@_handle_error
def dry_run(operation: str, only: str | None) -> None:
    """Preview what backup or restore would do without making changes."""
    from .dryrun import DryRunPreview, format_dry_run
    from .ignore import create_ignore_matcher

    sync = DotfileSync()
    sync._ensure_initialized()

    ignore_matcher = create_ignore_matcher(sync.repo_dir)
    preview = DryRunPreview(sync)

    if operation == "backup":
        result = preview.preview_backup(ignore_matcher=ignore_matcher)
    else:
        result = preview.preview_restore(
            only=only,
            render=True,
            ignore_matcher=ignore_matcher,
        )

    formatted = format_dry_run(result)
    console.print(formatted)
