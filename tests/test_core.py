"""Tests for dotfile-sync."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from dotfile_sync.core import (
    DotfileSync,
    DotfileSyncError,
    Manifest,
    NotInitializedError,
    _encode_repo_path,
)


@pytest.fixture
def tmp_home(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary home directory with some dotfiles."""
    home = tmp_path / "home"
    home.mkdir()

    # Create some dotfiles
    (home / ".bashrc").write_text("# My bashrc\nexport PATH=$PATH:/usr/local/bin\n")
    (home / ".gitconfig").write_text("[user]\n name = Test\n email = test@test.com\n")
    (home / ".config").mkdir()
    (home / ".config" / "nvim").mkdir(parents=True)
    nvim_init = '" Neovim config\nset number\n'
    (home / ".config" / "nvim" / "init.vim").write_text(nvim_init)
    (home / ".config" / "nvim" / "autoload").mkdir()
    plug_vim = '" Plug manager\n'
    (home / ".config" / "nvim" / "autoload" / "plug.vim").write_text(plug_vim)

    yield home


@pytest.fixture
def sync_repo(
    tmp_path: Path, tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[DotfileSync, None, None]:
    """Create an initialized dotfile-sync repo with a custom repo dir."""
    repo_dir = tmp_path / "dotfile-sync"
    sync = DotfileSync(repo_dir=repo_dir)
    sync.init()

    # Monkeypatch Path.home() so that relative path calculations work
    monkeypatch.setattr(Path, "home", lambda: tmp_home)

    yield sync


class TestManifest:
    """Tests for the Manifest class."""

    def test_empty_manifest(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        assert manifest.files == []

    def test_add_file(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        manifest.add_file("/home/user/.bashrc", "home/user/_bashrc")
        assert len(manifest.files) == 1
        assert manifest.files[0]["original_path"] == "/home/user/.bashrc"
        assert manifest.files[0]["repo_path"] == "home/user/_bashrc"
        assert "added_at" in manifest.files[0]

    def test_add_duplicate_is_noop(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        manifest.add_file("/home/user/.bashrc", "home/user/_bashrc")
        manifest.add_file("/home/user/.bashrc", "home/user/_bashrc")
        assert len(manifest.files) == 1

    def test_remove_file(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        manifest.add_file("/home/user/.bashrc", "home/user/_bashrc")
        assert manifest.remove_file("/home/user/.bashrc") is True
        assert len(manifest.files) == 0

    def test_remove_nonexistent(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        assert manifest.remove_file("/home/user/.bashrc") is False

    def test_is_tracked(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        assert manifest.is_tracked("/home/user/.bashrc") is False
        manifest.add_file("/home/user/.bashrc", "home/user/_bashrc")
        assert manifest.is_tracked("/home/user/.bashrc") is True

    def test_save_and_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.json"
        manifest = Manifest(path)
        manifest.add_file("/home/user/.bashrc", "home/user/_bashrc")
        manifest.save()

        # Reload
        manifest2 = Manifest(path)
        assert len(manifest2.files) == 1
        assert manifest2.files[0]["original_path"] == "/home/user/.bashrc"


class TestInit:
    """Tests for the init command."""

    def test_init_creates_repo(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        result = sync.init()
        assert "Initialized" in result
        assert repo_dir.exists()
        assert (repo_dir / ".git").exists()
        assert (repo_dir / "manifest.json").exists()
        assert (repo_dir / "files").exists()

    def test_init_idempotent(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init()
        result2 = sync.init()
        assert "already exists" in result2

    def test_init_with_remote(self, tmp_path: Path) -> None:
        from git import Repo

        repo_dir = tmp_path / "dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init(remote_url="https://github.com/example/dotfiles.git")

        repo = Repo(str(repo_dir))
        assert "origin" in [r.name for r in repo.remotes]


class TestTrack:
    """Tests for the track command."""

    def test_track_single_file(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        result = sync_repo.track(str(tmp_home / ".bashrc"))
        assert "Now tracking" in result

        manifest = Manifest(sync_repo.manifest_path)
        assert len(manifest.files) == 1

    def test_track_already_tracked(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.track(str(tmp_home / ".bashrc"))
        assert "Already tracking" in result

    def test_track_directory(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        result = sync_repo.track(str(tmp_home / ".config" / "nvim"))
        assert "Tracking" in result
        assert "file(s)" in result

        manifest = Manifest(sync_repo.manifest_path)
        # Should track init.vim and plug.vim
        assert len(manifest.files) == 2

    def test_track_nonexistent_path(self, sync_repo: DotfileSync) -> None:
        with pytest.raises(DotfileSyncError, match="does not exist"):
            sync_repo.track("/nonexistent/path/.bashrc")


class TestUntrack:
    """Tests for the untrack command."""

    def test_untrack_file(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.untrack(str(tmp_home / ".bashrc"))
        assert "Stopped tracking" in result

    def test_untrack_not_tracked(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        result = sync_repo.untrack(str(tmp_home / ".bashrc"))
        assert "Not currently tracked" in result

    def test_untrack_directory(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".config" / "nvim"))
        result = sync_repo.untrack(str(tmp_home / ".config" / "nvim"))
        assert "Stopped tracking" in result


class TestBackup:
    """Tests for the backup command."""

    def test_backup_copies_files(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.backup()
        assert "Backed up 1 file" in result

    def test_backup_with_message(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.backup(message="initial backup")
        assert "initial backup" in result

    def test_backup_no_tracked_files(self, sync_repo: DotfileSync) -> None:
        result = sync_repo.backup()
        assert "No files tracked" in result

    def test_backup_file_content_preserved(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        content = "# My bashrc\n"
        (tmp_home / ".bashrc").write_text(content)
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()

        manifest = Manifest(sync_repo.manifest_path)
        repo_path = sync_repo.files_dir / manifest.files[0]["repo_path"]
        assert repo_path.read_text() == content


class TestRestore:
    """Tests for the restore command."""

    def test_restore_copies_files(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        original_content = "# Original bashrc\n"
        (tmp_home / ".bashrc").write_text(original_content)
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()

        # Modify the original
        (tmp_home / ".bashrc").write_text("# Modified bashrc\n")

        # Restore
        result = sync_repo.restore()
        assert "Restored 1 file" in result
        assert (tmp_home / ".bashrc").read_text() == original_content

    def test_restore_single_file(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.track(str(tmp_home / ".gitconfig"))
        sync_repo.backup()

        result = sync_repo.restore(only=str(tmp_home / ".bashrc"))
        assert "Restored 1 file" in result

    def test_restore_no_manifest(self, sync_repo: DotfileSync) -> None:
        result = sync_repo.restore()
        assert "No files in manifest" in result


class TestDiff:
    """Tests for the diff command."""

    def test_diff_no_changes(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()
        result = sync_repo.diff()
        assert "up to date" in result

    def test_diff_with_modification(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()

        # Modify the file
        (tmp_home / ".bashrc").write_text("# Changed!\n")

        result = sync_repo.diff()
        assert "MODIFIED" in result

    def test_diff_new_file(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        # Don't backup yet
        result = sync_repo.diff()
        assert "NEW" in result

    def test_diff_deleted_file(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        sync_repo.backup()

        # Delete the original
        (tmp_home / ".bashrc").unlink()

        result = sync_repo.diff()
        assert "DELETED" in result


class TestListTracked:
    """Tests for the list command."""

    def test_list_tracked_files(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        result = sync_repo.list_tracked()
        assert "bashrc" in result
        assert "Tracked files:" in result

    def test_list_no_files(self, sync_repo: DotfileSync) -> None:
        result = sync_repo.list_tracked()
        assert "No files tracked" in result


class TestEncodeRepoPath:
    """Tests for path encoding."""

    def test_encode_dotfile(self) -> None:
        assert _encode_repo_path("home/user/.bashrc") == "home/user/_bashrc"

    def test_encode_nested_dotfile(self) -> None:
        result = _encode_repo_path("home/user/.config/nvim/init.vim")
        assert result == "home/user/_config/nvim/init.vim"

    def test_encode_no_dot(self) -> None:
        assert _encode_repo_path("home/user/config.yaml") == "home/user/config.yaml"

    def test_encode_multiple_dots(self) -> None:
        result = _encode_repo_path("home/user/.config/.hidden")
        assert result == "home/user/_config/_hidden"


class TestNotInitialized:
    """Tests for error handling when not initialized."""

    def test_track_without_init(self, tmp_path: Path) -> None:
        sync = DotfileSync(repo_dir=tmp_path / "nonexistent")
        with pytest.raises(NotInitializedError):
            sync.track("/home/user/.bashrc")

    def test_backup_without_init(self, tmp_path: Path) -> None:
        sync = DotfileSync(repo_dir=tmp_path / "nonexistent")
        with pytest.raises(NotInitializedError):
            sync.backup()
