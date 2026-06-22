"""Dry-run preview for backup and restore operations.

Shows what would happen without making any changes to disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import DotfileSync, Manifest
from .hooks import HookEvent, create_hook_runner


class DryRunResult:
    def __init__(self, operation: str) -> None:
        self.operation = operation
        self.actions: list[str] = []
        self.skipped: list[str] = []
        self.errors: list[str] = []
        self.template_count = 0
        self.ignore_count = 0

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def __repr__(self) -> str:
        return (
            f"DryRunResult({self.operation}: "
            f"{self.action_count} actions, "
            f"{self.skipped_count} skipped, "
            f"{self.error_count} errors)"
        )


class DryRunPreview:
    """Preview what backup/restore would do without making changes."""

    def __init__(self, sync: DotfileSync) -> None:
        self.sync = sync

    def preview_backup(
        self,
        ignore_matcher: Any | None = None,
    ) -> DryRunResult:
        """Preview what backup would do.

        Args:
            ignore_matcher: Optional ignore matcher to filter files.

        Returns:
            DryRunResult with planned actions.
        """
        result = DryRunResult("backup")

        self.sync._ensure_initialized()
        manifest = Manifest(self.sync.manifest_path)

        # Check pre-backup hooks (even if no files tracked)
        hook_runner = create_hook_runner(self.sync.repo_dir)
        hook_commands = hook_runner.config.get_hooks(HookEvent.PRE_BACKUP)
        if hook_commands:
            result.actions.append(f"Would run {len(hook_commands)} pre-backup hook(s)")

        if not manifest.files:
            result.skipped.append("No files tracked")
            # Still check post-backup hooks
            post_hooks = hook_runner.config.get_hooks(HookEvent.POST_BACKUP)
            if post_hooks:
                result.actions.append(f"Would run {len(post_hooks)} post-backup hook(s)")
            return result

        for entry in manifest.files:
            original = Path(entry["original_path"])
            repo_path = self.sync.files_dir / entry["repo_path"]

            # Check ignore patterns
            if ignore_matcher and ignore_matcher.is_ignored(original):
                result.ignore_count += 1
                continue

            if not original.exists():
                result.skipped.append(f"{entry['original_path']} (deleted)")
                continue

            if entry.get("is_template"):
                result.template_count += 1
                template_repo = self.sync.templates_dir / entry["repo_path"]
                if repo_path.exists():
                    try:
                        orig_bytes = original.read_bytes()
                        repo_bytes = repo_path.read_bytes()
                        if orig_bytes == repo_bytes:
                            result.skipped.append(f"{entry['original_path']} [T] (unchanged)")
                            continue
                    except OSError:
                        pass
                result.actions.append(
                    f"Backup (template): {entry['original_path']} -> {template_repo}"
                )
                result.actions.append(f"Render snapshot: {entry['original_path']} -> {repo_path}")
            else:
                if repo_path.exists():
                    try:
                        if original.read_bytes() == repo_path.read_bytes():
                            result.skipped.append(f"{entry['original_path']} (unchanged)")
                            continue
                    except OSError:
                        pass
                result.actions.append(f"Backup: {entry['original_path']} -> {repo_path}")

        # Post-backup hooks
        post_hooks = hook_runner.config.get_hooks(HookEvent.POST_BACKUP)
        if post_hooks:
            result.actions.append(f"Would run {len(post_hooks)} post-backup hook(s)")

        if result.ignore_count:
            result.skipped.append(f"{result.ignore_count} ignored by patterns")

        return result

    def preview_restore(
        self,
        only: str | None = None,
        *,
        render: bool = True,
        ignore_matcher: Any | None = None,
    ) -> DryRunResult:
        """Preview what restore would do.

        Args:
            only: If set, only preview this specific file.
            render: If True, preview template rendering.
            ignore_matcher: Optional ignore matcher.

        Returns:
            DryRunResult with planned actions.
        """
        result = DryRunResult("restore")

        self.sync._ensure_initialized()
        manifest = Manifest(self.sync.manifest_path)

        if not manifest.files:
            result.skipped.append("No files in manifest")
            return result

        for entry in manifest.files:
            if only and entry["original_path"] != only:
                continue

            original = Path(entry["original_path"])
            repo_path = self.sync.files_dir / entry["repo_path"]

            if ignore_matcher and ignore_matcher.is_ignored(original):
                result.ignore_count += 1
                continue

            if entry.get("is_template") and render:
                template_repo = self.sync.templates_dir / entry["repo_path"]
                if not template_repo.exists():
                    result.skipped.append(f"{entry['original_path']} [T] (template missing)")
                    continue

                if original.exists():
                    try:
                        context = self.sync._build_render_context()
                        engine = self.sync._get_template_engine()
                        template_content = template_repo.read_text(encoding="utf-8")
                        rendered = engine.render(template_content, context)
                        orig_content = original.read_text(encoding="utf-8")
                        if orig_content == rendered:
                            result.skipped.append(f"{entry['original_path']} [T] (up to date)")
                            continue
                    except Exception:
                        pass
                result.actions.append(f"Render (template): {template_repo} -> {original}")
                result.template_count += 1
            else:
                if not repo_path.exists():
                    result.skipped.append(f"{entry['original_path']} (not in repo)")
                    continue

                if original.exists():
                    try:
                        if original.read_bytes() == repo_path.read_bytes():
                            result.skipped.append(f"{entry['original_path']} (up to date)")
                            continue
                    except OSError:
                        pass
                result.actions.append(f"Restore: {repo_path} -> {original}")

        if result.ignore_count:
            result.skipped.append(f"{result.ignore_count} ignored by patterns")

        return result


def format_dry_run(result: DryRunResult) -> str:
    """Format a dry-run result for display.

    Args:
        result: The dry-run result to format.

    Returns:
        Formatted string for CLI output.
    """
    lines = [f"[bold]Dry-run preview: {result.operation}[/bold]", ""]

    if result.errors:
        lines.append(f"[red]Errors ({len(result.errors)}):[/red]")
        for err in result.errors:
            lines.append(f"  ✗ {err}")
        lines.append("")

    if result.actions:
        lines.append(f"[green]Actions ({result.action_count}):[/green]")
        for action in result.actions:
            lines.append(f"  → {action}")
    else:
        lines.append("[dim]No actions needed[/dim]")

    if result.skipped:
        lines.append("")
        lines.append(f"[yellow]Skipped ({result.skipped_count}):[/yellow]")
        for skip in result.skipped:
            lines.append(f"  ⊘ {skip}")

    if result.template_count:
        lines.append(f"\n[cyan]Template files: {result.template_count}[/cyan]")

    if result.ignore_count:
        lines.append(f"[dim]Ignored: {result.ignore_count}[/dim]")

    return "\n".join(lines)
