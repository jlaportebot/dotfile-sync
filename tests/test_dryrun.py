"""Tests for dry-run preview functionality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dotfile_sync.core import DotfileSync, Manifest
from dotfile_sync.dryrun import DryRunPreview, DryRunResult, format_dry_run
from dotfile_sync.errors import DotfileSyncError


class TestDryRunResult:
    """Tests for DryRunResult."""

    def test_empty_result(self) -> None:
        result = DryRunResult("backup")
        assert result.action_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 0

    def test_with_actions(self) -> None:
        result = DryRunResult("backup")
        result.actions.append("Backup: file1 -> repo/file1")
        assert result.action_count == 1

    def test_repr(self) -> None:
        result = DryRunResult("backup")
        result.actions.append("a")
        result.skipped.append("s")
        assert "1 actions" in repr(result)
        assert "1 skipped" in repr(result)


class TestDryRunPreview:
    """Tests for the DryRunPreview class."""

    def test_preview_backup_no_files(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / ".dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init()

        preview = DryRunPreview(sync)
        result = preview.preview_backup()
        assert result.operation == "backup"
        assert result.action_count == 0

    def test_preview_backup_with_files(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / ".dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init()

        # Create a tracked file
        test_file = tmp_path / ".testrc"
        test_file.write_text("test content")

        manifest = Manifest(sync.manifest_path)
        manifest.add_file(str(test_file), "_testrc")
        manifest.save()

        preview = DryRunPreview(sync)
        result = preview.preview_backup()
        assert result.action_count >= 1

    def test_preview_backup_unchanged(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / ".dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init()

        test_file = tmp_path / ".testrc"
        test_file.write_text("content")

        manifest = Manifest(sync.manifest_path)
        manifest.add_file(str(test_file), "_testrc")
        manifest.save()

        # First, do a real backup
        sync.backup()

        # Now preview — should show files as unchanged
        preview = DryRunPreview(sync)
        result = preview.preview_backup()
        # The file hasn't changed since backup, so it should be skipped
        assert result.skipped_count >= 1

    def test_preview_restore_no_files(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / ".dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init()

        preview = DryRunPreview(sync)
        result = preview.preview_restore()
        assert result.operation == "restore"
        assert result.action_count == 0

    def test_preview_restore_with_files(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / ".dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init()

        test_file = tmp_path / ".testrc"
        test_file.write_text("content")

        manifest = Manifest(sync.manifest_path)
        manifest.add_file(str(test_file), "_testrc")
        manifest.save()

        # Backup first
        sync.backup()

        # Modify local file
        test_file.write_text("modified content")

        # Preview restore
        preview = DryRunPreview(sync)
        result = preview.preview_restore()
        assert result.action_count >= 1

    def test_preview_restore_specific_file(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / ".dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init()

        test_file = tmp_path / ".testrc"
        test_file.write_text("content")

        manifest = Manifest(sync.manifest_path)
        manifest.add_file(str(test_file), "_testrc")
        manifest.save()
        sync.backup()

        test_file.write_text("modified")
        preview = DryRunPreview(sync)
        result = preview.preview_restore(only=str(test_file))
        assert result.action_count == 1

    def test_preview_with_hooks(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / ".dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init()

        from dotfile_sync.hooks import HookConfig, HookEvent

        hook_config = HookConfig(repo_dir / "hooks.json")
        hook_config.add_hook(HookEvent.PRE_BACKUP, "echo pre-backup")

        preview = DryRunPreview(sync)
        result = preview.preview_backup()
        # Should mention hooks in actions
        hook_actions = [a for a in result.actions if "hook" in a.lower()]
        assert len(hook_actions) >= 1


class TestFormatDryRun:
    """Tests for the format_dry_run function."""

    def test_format_empty_result(self) -> None:
        result = DryRunResult("backup")
        formatted = format_dry_run(result)
        assert "backup" in formatted
        assert "No actions" in formatted

    def test_format_with_actions(self) -> None:
        result = DryRunResult("restore")
        result.actions.append("Restore: a -> b")
        formatted = format_dry_run(result)
        assert "Restore" in formatted
        assert "a -> b" in formatted

    def test_format_with_skipped(self) -> None:
        result = DryRunResult("backup")
        result.skipped.append("file.txt (unchanged)")
        formatted = format_dry_run(result)
        assert "Skipped" in formatted
        assert "unchanged" in formatted

    def test_format_with_errors(self) -> None:
        result = DryRunResult("backup")
        result.errors.append("Permission denied")
        formatted = format_dry_run(result)
        assert "Errors" in formatted
        assert "Permission denied" in formatted

    def test_format_with_templates_and_ignores(self) -> None:
        result = DryRunResult("restore")
        result.template_count = 3
        result.ignore_count = 2
        formatted = format_dry_run(result)
        assert "3" in formatted
        assert "2" in formatted
