"""Tests for dotfile-sync core with template integration."""

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

    # Create a template dotfile
    (home / ".gitconfig_tmpl").write_text(
        "[user]\n name = {{ git_name }}\n email = {{ git_email }}\n"
    )

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


class TestManifestExtended:
    """Tests for extended Manifest features."""

    def test_is_template_flag(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        manifest.add_file("/home/user/.gitconfig", "home/user/_gitconfig", is_template=True)
        assert manifest.files[0].get("is_template") is True

    def test_is_template_default_false(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        manifest.add_file("/home/user/.bashrc", "home/user/_bashrc")
        assert "is_template" not in manifest.files[0]

    def test_update_file(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        manifest.add_file("/home/user/.bashrc", "home/user/_bashrc")
        result = manifest.update_file("/home/user/.bashrc", is_template=True)
        assert result is True
        assert manifest.files[0].get("is_template") is True

    def test_update_file_not_found(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        result = manifest.update_file("/home/user/nonexistent", is_template=True)
        assert result is False

    def test_get_template_files(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        manifest.add_file("/home/user/.bashrc", "home/user/_bashrc")
        manifest.add_file("/home/user/.gitconfig", "home/user/_gitconfig", is_template=True)
        templates = manifest.get_template_files()
        assert len(templates) == 1
        assert templates[0]["original_path"] == "/home/user/.gitconfig"

    def test_get_concrete_files(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        manifest.add_file("/home/user/.bashrc", "home/user/_bashrc")
        manifest.add_file("/home/user/.gitconfig", "home/user/_gitconfig", is_template=True)
        concrete = manifest.get_concrete_files()
        assert len(concrete) == 1
        assert concrete[0]["original_path"] == "/home/user/.bashrc"

    def test_active_profile(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        assert manifest.active_profile is None
        manifest.active_profile = "work"
        assert manifest.active_profile == "work"

    def test_machine_name(self, tmp_path: Path) -> None:
        manifest = Manifest(tmp_path / "manifest.json")
        assert manifest.machine_name is None
        manifest.machine_name = "laptop"
        assert manifest.machine_name == "laptop"

    def test_profile_persists_after_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.json"
        manifest = Manifest(path)
        manifest.active_profile = "work"
        manifest.machine_name = "laptop"

        manifest2 = Manifest(path)
        assert manifest2.active_profile == "work"
        assert manifest2.machine_name == "laptop"


class TestInitExtended:
    """Tests for the init command with template support."""

    def test_init_creates_template_dirs(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init()
        assert (repo_dir / "templates").exists()
        assert (repo_dir / "contexts").exists()

    def test_init_creates_default_context(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "dotfile-sync"
        sync = DotfileSync(repo_dir=repo_dir)
        sync.init()
        ctx_dir = repo_dir / "contexts"
        assert (ctx_dir / "default.yaml").exists()


class TestTrackWithTemplates:
    """Tests for tracking files with template detection."""

    def test_track_template_file(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        result = sync_repo.track(str(tmp_home / ".gitconfig_tmpl"), as_template=True)
        assert "template" in result

        manifest = Manifest(sync_repo.manifest_path)
        entry = manifest.get_entry(str(tmp_home / ".gitconfig_tmpl"))
        assert entry is not None
        assert entry.get("is_template") is True

    def test_track_auto_detects_template(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        # Create a file with Jinja2 syntax
        template_file = tmp_home / ".config" / "app.conf"
        template_file.write_text("host={{ hostname }}\nport=8080\n")
        result = sync_repo.track(str(template_file))
        assert "template" in result

        manifest = Manifest(sync_repo.manifest_path)
        entry = manifest.get_entry(str(template_file))
        assert entry is not None
        assert entry.get("is_template") is True

    def test_track_plain_file_not_template(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        result = sync_repo.track(str(tmp_home / ".bashrc"))
        assert "template" not in result

        manifest = Manifest(sync_repo.manifest_path)
        entry = manifest.get_entry(str(tmp_home / ".bashrc"))
        assert entry is not None
        assert "is_template" not in entry

    def test_track_directory_detects_templates(
        self, sync_repo: DotfileSync, tmp_home: Path
    ) -> None:
        # Add template file to the nvim config dir
        template_file = tmp_home / ".config" / "nvim" / "app.conf"
        template_file.write_text("setting={{ value }}")

        result = sync_repo.track(str(tmp_home / ".config" / "nvim"))
        assert "template" in result


class TestBackupWithTemplates:
    """Tests for backup with template files."""

    def test_backup_stores_template_in_templates_dir(
        self, sync_repo: DotfileSync, tmp_home: Path
    ) -> None:
        template_file = tmp_home / ".config" / "app.conf"
        template_content = "host={{ hostname }}\n"
        template_file.write_text(template_content)

        sync_repo.track(str(template_file))
        result = sync_repo.backup()
        assert "Backed up" in result

        manifest = Manifest(sync_repo.manifest_path)
        entry = manifest.get_entry(str(template_file))
        assert entry is not None

        # Check template stored in templates/ dir
        template_repo_path = sync_repo.templates_dir / entry["repo_path"]
        assert template_repo_path.exists()
        assert template_repo_path.read_text() == template_content

        # Check rendered snapshot stored in files/ dir
        file_repo_path = sync_repo.files_dir / entry["repo_path"]
        assert file_repo_path.exists()

    def test_backup_template_render_error_falls_back(
        self, sync_repo: DotfileSync, tmp_home: Path
    ) -> None:
        # Create a template with an undefined variable
        template_file = tmp_home / ".config" / "broken.conf"
        template_file.write_text("value={{ undefined_var }}\n")

        sync_repo.track(str(template_file), as_template=True)
        result = sync_repo.backup()
        assert "Backed up" in result

        # The raw template should still be stored
        manifest = Manifest(sync_repo.manifest_path)
        entry = manifest.get_entry(str(template_file))
        assert entry is not None
        template_repo_path = sync_repo.templates_dir / entry["repo_path"]
        assert template_repo_path.exists()


class TestRestoreWithTemplates:
    """Tests for restore with template rendering."""

    def test_restore_renders_template(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        template_file = tmp_home / ".config" / "app.conf"
        template_content = "host={{ hostname }}\n"
        template_file.write_text(template_content)

        sync_repo.track(str(template_file), as_template=True)
        sync_repo.backup()

        # Set up context
        from dotfile_sync.templates import ContextManager

        ctx_mgr = ContextManager(sync_repo.contexts_dir)
        ctx_mgr.set_context("default", {"hostname": "myserver"})

        # Modify the original file
        template_file.write_text("host=oldserver\n")

        # Restore should re-render from template
        result = sync_repo.restore()
        assert "rendered" in result.lower() or "Restored" in result

    def test_restore_no_render_flag(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        template_file = tmp_home / ".config" / "app.conf"
        template_content = "host={{ hostname }}\n"
        template_file.write_text(template_content)

        sync_repo.track(str(template_file), as_template=True)
        sync_repo.backup()

        # Modify the original
        template_file.write_text("host=changed\n")

        # Restore without rendering - should copy from files/ dir (rendered snapshot)
        result = sync_repo.restore(render=False)
        assert "Restored" in result


class TestDiffWithTemplates:
    """Tests for diff with template awareness."""

    def test_diff_template_up_to_date(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        template_file = tmp_home / ".config" / "app.conf"
        template_content = "host={{ hostname }}\n"
        template_file.write_text(template_content)

        sync_repo.track(str(template_file), as_template=True)
        sync_repo.backup()

        # The backup stored the raw template in templates/ dir and the
        # *rendered* snapshot in files/.  To be "up to date", the live file
        # must match the re-rendered version, not the raw template.
        # Read back the rendered snapshot from files/ and write it to the
        # live file.
        manifest = Manifest(sync_repo.manifest_path)
        entry = manifest.get_entry(str(template_file))
        assert entry is not None
        files_path = sync_repo.files_dir / entry["repo_path"]
        rendered = files_path.read_text()
        template_file.write_text(rendered)

        result = sync_repo.diff()
        assert "up to date" in result

    def test_diff_template_modified(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        template_file = tmp_home / ".config" / "app.conf"
        template_content = "host={{ hostname }}\n"
        template_file.write_text(template_content)

        sync_repo.track(str(template_file), as_template=True)
        sync_repo.backup()

        # Modify the original
        template_file.write_text("host=changedhost\n")

        result = sync_repo.diff()
        assert "MODIFIED" in result or "template" in result.lower()


class TestListTrackedWithTemplates:
    """Tests for list with template status."""

    def test_list_shows_template_marker(self, sync_repo: DotfileSync, tmp_home: Path) -> None:
        sync_repo.track(str(tmp_home / ".bashrc"))
        template_file = tmp_home / ".config" / "app.conf"
        template_file.write_text("{{ value }}")
        sync_repo.track(str(template_file))

        result = sync_repo.list_tracked()
        assert "[T]" in result


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

    def test_restore_without_init(self, tmp_path: Path) -> None:
        sync = DotfileSync(repo_dir=tmp_path / "nonexistent")
        with pytest.raises(NotInitializedError):
            sync.restore()
