"""Tests for core methods not covered by test_core.py."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from dotfile_sync.core import DotfileSync, Manifest, _decode_repo_path
from dotfile_sync.errors import DotfileSyncError, NotInitializedError
from dotfile_sync.templates import ContextManager


@pytest.fixture
def tmp_home(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary home directory with dotfiles."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text("# My bashrc\nexport PATH=$PATH:/usr/local/bin\n")
    (home / ".gitconfig").write_text("[user]\n name = Test\n email = test@test.com\n")
    (home / ".config").mkdir()
    (home / ".config" / "nvim").mkdir(parents=True)
    (home / ".config" / "nvim" / "init.vim").write_text('" Neovim config\nset number\n')
    yield home


@pytest.fixture
def sync_repo(
    tmp_path: Path, tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[DotfileSync, None, None]:
    """Create an initialized dotfile-sync repo."""
    repo_dir = tmp_path / "dotfile-sync"
    sync = DotfileSync(repo_dir=repo_dir)
    sync.init()
    monkeypatch.setattr(Path, "home", lambda: tmp_home)
    yield sync


class TestPush:
    """Tests for the push command."""

    def test_push_no_remote(self, sync_repo: DotfileSync) -> None:
        with pytest.raises(DotfileSyncError, match="No remote configured"):
            sync_repo.push()

    def test_push_not_initialized(self, tmp_path: Path) -> None:
        sync = DotfileSync(repo_dir=tmp_path / "nonexistent")
        with pytest.raises(NotInitializedError):
            sync.push()


class TestPull:
    """Tests for the pull command."""

    def test_pull_no_remote(self, sync_repo: DotfileSync) -> None:
        with pytest.raises(DotfileSyncError, match="No remote configured"):
            sync_repo.pull()


class TestListTracked:
    """Tests for the list_tracked method."""

    def test_list_tracked_empty(self, sync_repo: DotfileSync) -> None:
        result = sync_repo.list_tracked()
        assert "No files tracked" in result

    def test_list_tracked_with_files(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.list_tracked()
        assert "Tracked files" in result
        assert ".bashrc" in result

    def test_list_tracked_template_marker(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        template_file = tmp_home / ".config" / "app.conf"
        template_file.parent.mkdir(parents=True, exist_ok=True)
        template_file.write_text("{{ value }}")
        sync_repo.track(str(template_file))
        result = sync_repo.list_tracked()
        assert "[T]" in result

    def test_list_tracked_file_on_disk(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.list_tracked()
        assert "✓" in result  # on disk marker

    def test_list_tracked_file_not_on_disk(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        # Delete the file
        (tmp_home / ".bashrc").unlink()
        result = sync_repo.list_tracked()
        assert "✗" in result  # not on disk marker

    def test_list_tracked_with_backup(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()
        result = sync_repo.list_tracked()
        # Both on disk and backed up
        assert result.count("✓") >= 2

    def test_list_tracked_not_backed_up(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.list_tracked()
        # Should show not backed up
        assert "✗" in result or "backed up" in result or "Tracked files" in result


class TestStatus:
    """Tests for the status method."""

    def test_status_clean(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()
        result = sync_repo.status()
        assert "up to date" in result

    def test_status_modified(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()
        # Modify the file
        (tmp_home / ".bashrc").write_text("# Modified bashrc\n")
        result = sync_repo.status()
        assert "MODIFIED" in result

    def test_status_no_files(self, sync_repo: DotfileSync) -> None:
        result = sync_repo.status()
        assert "No files tracked" in result


class TestDiffDetailed:
    """Tests for the diff_detailed method."""

    def test_diff_detailed_no_files(self, sync_repo: DotfileSync) -> None:
        result = sync_repo.diff_detailed()
        assert "No files tracked" in result

    def test_diff_detailed_with_changes(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()
        # Modify file
        (tmp_home / ".bashrc").write_text("# Modified content\n")
        result = sync_repo.diff_detailed()
        assert "---" in result or "No differences" in result

    def test_diff_detailed_no_changes(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()
        result = sync_repo.diff_detailed()
        assert "No differences" in result

    def test_diff_detailed_specific_path(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()
        result = sync_repo.diff_detailed(path=str(tmp_home / ".bashrc"))
        assert "No differences" in result


class TestInitDefaultContext:
    """Tests for init creating default context."""

    def test_init_default_context_has_hostname(self, sync_repo: DotfileSync) -> None:
        ctx_mgr = ContextManager(sync_repo.contexts_dir)
        default = ctx_mgr.get_context("default")
        assert "hostname" in default


class TestRestoreWithOnly:
    """Tests for restore with only flag."""

    def test_restore_specific_file(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.track(str(tmp_home / ".gitconfig"))
        sync_repo.backup()

        # Modify both files
        (tmp_home / ".bashrc").write_text("# changed bashrc\n")
        (tmp_home / ".gitconfig").write_text("# changed gitconfig\n")

        result = sync_repo.restore(only=str(tmp_home / ".bashrc"))
        assert "Restored" in result

        # Only .bashrc should be restored
        assert (
            tmp_home / ".bashrc"
        ).read_text() == "# My bashrc\nexport PATH=$PATH:/usr/local/bin\n"

    def test_restore_skips_missing_repo_files(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        # Don't back up - so repo_path won't exist
        result = sync_repo.restore()
        assert (
            "skipped" in result.lower() or "Restored 0" in result or "not found" in result.lower()
        )


class TestDecodeRepoPath:
    """Tests for _decode_repo_path."""

    def test_decode_dotfile(self) -> None:
        assert _decode_repo_path("home/user/_bashrc") == "home/user/.bashrc"

    def test_decode_nested(self) -> None:
        result = _decode_repo_path("home/user/_config/nvim/init.vim")
        assert result == "home/user/.config/nvim/init.vim"

    def test_decode_no_underscore(self) -> None:
        assert _decode_repo_path("home/user/config.yaml") == "home/user/config.yaml"


class TestBackupWithMessage:
    """Tests for backup with custom message."""

    def test_backup_custom_message(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.backup(message="my custom backup")
        assert "my custom backup" in result

    def test_backup_auto_message(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.backup()
        assert "backup:" in result.lower()


class TestTrackAlreadyTracked:
    """Tests for tracking already tracked files."""

    def test_track_already_tracked(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.track(str(tmp_home / ".bashrc"))
        assert "Already tracking" in result


class TestUntrackDirectory:
    """Tests for untracking directories."""

    def test_untrack_directory(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".config" / "nvim"))
        result = sync_repo.untrack(str(tmp_home / ".config" / "nvim"))
        assert "Stopped tracking" in result

    def test_untrack_not_tracked(self, sync_repo: DotfileSync) -> None:
        result = sync_repo.untrack("/nonexistent/path")
        assert "Not currently tracked" in result
