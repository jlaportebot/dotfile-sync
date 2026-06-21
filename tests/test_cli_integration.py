"""Integration tests for dotfile-sync CLI commands."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from dotfile_sync.cli import main
from dotfile_sync.core import DotfileSync


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def tmp_home(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary home directory with some dotfiles."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text("# My bashrc\nexport PATH=$PATH:/usr/local/bin\n")
    (home / ".gitconfig").write_text("[user]\n name = Test\n email = test@test.com\n")
    (home / ".config").mkdir()
    (home / ".config" / "app.conf").mkdir(parents=True, exist_ok=True)
    app_conf = home / ".config" / "app.conf" / "settings.conf"
    app_conf.parent.mkdir(parents=True, exist_ok=True)
    app_conf.write_text("host=localhost\nport=8080\n")
    yield home


@pytest.fixture
def env_repo(
    tmp_path: Path, tmp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Path, None, None]:
    """Create an initialized dotfile-sync repo and monkeypatch home + repo dir."""
    repo_dir = tmp_path / "dotfile-sync"
    sync = DotfileSync(repo_dir=repo_dir)
    sync.init()
    monkeypatch.setattr(Path, "home", lambda: tmp_home)
    monkeypatch.setenv("DOTFILE_SYNC_DIR", str(repo_dir))
    yield repo_dir


class TestCLIInit:
    """Tests for the init CLI command."""

    def test_init_success(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo_dir = tmp_path / "test-repo"
        monkeypatch.setenv("DOTFILE_SYNC_DIR", str(repo_dir))
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.init.return_value = "Initialized dotfile-sync repository"
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert "Initialized" in result.output

    def test_init_with_remote(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo_dir = tmp_path / "test-repo"
        monkeypatch.setenv("DOTFILE_SYNC_DIR", str(repo_dir))
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.init.return_value = "Initialized dotfile-sync repository"
            result = runner.invoke(main, ["init", "--remote", "https://github.com/test/repo.git"])
            assert result.exit_code == 0

    def test_init_already_exists(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo_dir = tmp_path / "test-repo"
        monkeypatch.setenv("DOTFILE_SYNC_DIR", str(repo_dir))
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.init.return_value = "Repository already exists"
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert "already exists" in result.output


class TestCLITrack:
    """Tests for the track CLI command."""

    def test_track_file(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.track.return_value = "Now tracking: /home/user/.bashrc"
            result = runner.invoke(main, ["track", "/home/user/.bashrc"])
            assert result.exit_code == 0
            assert "Now tracking" in result.output

    def test_track_as_template(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.track.return_value = "Now tracking: /home/user/.gitconfig (template)"
            result = runner.invoke(main, ["track", "--template", "/home/user/.gitconfig"])
            assert result.exit_code == 0
            assert "template" in result.output

    def test_track_nonexistent_raises(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.track.side_effect = SystemExit(1)
            from dotfile_sync.errors import DotfileSyncError

            mock_inst.track.side_effect = DotfileSyncError("Path does not exist")
            result = runner.invoke(main, ["track", "/nonexistent/path"])
            assert result.exit_code == 1


class TestCLIUntrack:
    """Tests for the untrack CLI command."""

    def test_untrack_file(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.untrack.return_value = "Stopped tracking: /home/user/.bashrc"
            result = runner.invoke(main, ["untrack", "/home/user/.bashrc"])
            assert result.exit_code == 0
            assert "Stopped tracking" in result.output

    def test_untrack_not_tracked(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.untrack.return_value = "Not currently tracked: /home/user/.vimrc"
            result = runner.invoke(main, ["untrack", "/home/user/.vimrc"])
            assert result.exit_code == 0


class TestCLIList:
    """Tests for the list CLI command."""

    def test_list_tracked(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.list_tracked.return_value = "Tracked files:\n  .bashrc"
            result = runner.invoke(main, ["list"])
            assert result.exit_code == 0
            assert "Tracked files" in result.output

    def test_list_empty(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.list_tracked.return_value = "No files tracked."
            result = runner.invoke(main, ["list"])
            assert result.exit_code == 0


class TestCLIBackup:
    """Tests for the backup CLI command."""

    def test_backup_success(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.backup.return_value = "Backed up 5 file(s)."
            result = runner.invoke(main, ["backup"])
            assert result.exit_code == 0
            assert "Backed up" in result.output

    def test_backup_with_message(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.backup.return_value = "Backed up 5 file(s). Committed as: custom message"
            result = runner.invoke(main, ["backup", "--message", "custom message"])
            assert result.exit_code == 0

    def test_backup_no_files(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.backup.return_value = "No files tracked."
            result = runner.invoke(main, ["backup"])
            assert result.exit_code == 0


class TestCLIRestore:
    """Tests for the restore CLI command."""

    def test_restore_success(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.restore.return_value = "Restored 3 file(s)"
            result = runner.invoke(main, ["restore"])
            assert result.exit_code == 0
            assert "Restored" in result.output

    def test_restore_with_only(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.restore.return_value = "Restored 1 file(s)"
            result = runner.invoke(main, ["restore", "--only", "/home/user/.bashrc"])
            assert result.exit_code == 0

    def test_restore_no_render(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.restore.return_value = "Restored 3 file(s)"
            result = runner.invoke(main, ["restore", "--no-render"])
            assert result.exit_code == 0
            mock_inst.restore.assert_called_once_with(only=None, render=False)


class TestCLIDiff:
    """Tests for the diff CLI command."""

    def test_diff_success(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.diff.return_value = "Status of tracked files:\n  .bashrc: up to date"
            result = runner.invoke(main, ["diff"])
            assert result.exit_code == 0
            assert "up to date" in result.output

    def test_diff_no_files(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.diff.return_value = "No files tracked."
            result = runner.invoke(main, ["diff"])
            assert result.exit_code == 0


class TestCLIStatus:
    """Tests for the status CLI command."""

    def test_status_clean(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.status.return_value = "All tracked files are up to date."
            result = runner.invoke(main, ["status"])
            assert result.exit_code == 0
            assert "up to date" in result.output


class TestCLIPush:
    """Tests for the push CLI command."""

    def test_push_no_remote(self, runner: CliRunner) -> None:
        from dotfile_sync.errors import DotfileSyncError

        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.push.side_effect = DotfileSyncError("No remote configured")
            result = runner.invoke(main, ["push"])
            assert result.exit_code == 1

    def test_push_success(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.push.return_value = "Pushed to remote."
            result = runner.invoke(main, ["push"])
            assert result.exit_code == 0
            assert "Pushed" in result.output


class TestCLIPull:
    """Tests for the pull CLI command."""

    def test_pull_no_remote(self, runner: CliRunner) -> None:
        from dotfile_sync.errors import DotfileSyncError

        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.pull.side_effect = DotfileSyncError("No remote configured")
            result = runner.invoke(main, ["pull"])
            assert result.exit_code == 1

    def test_pull_success(self, runner: CliRunner) -> None:
        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.pull.return_value = "Pulled from remote. Restored 5 file(s)"
            result = runner.invoke(main, ["pull"])
            assert result.exit_code == 0
            assert "Pulled" in result.output


class TestCLIErrorHandling:
    """Tests for CLI error handling via _handle_error decorator."""

    def test_not_initialized_error(self, runner: CliRunner) -> None:
        from dotfile_sync.errors import NotInitializedError

        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.backup.side_effect = NotInitializedError("not initialized")
            result = runner.invoke(main, ["backup"])
            assert result.exit_code == 1

    def test_dotfile_sync_error(self, runner: CliRunner) -> None:
        from dotfile_sync.errors import DotfileSyncError

        with patch("dotfile_sync.cli.DotfileSync") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.backup.side_effect = DotfileSyncError("something went wrong")
            result = runner.invoke(main, ["backup"])
            assert result.exit_code == 1


class TestCLITemplateScan:
    """Tests for the template scan CLI command."""

    def test_scan_template_file(self, runner: CliRunner, tmp_path: Path) -> None:
        template_file = tmp_path / "config.conf"
        template_file.write_text("host={{ hostname }}\nport={{ port }}\n")
        result = runner.invoke(main, ["template", "scan", str(template_file)])
        assert result.exit_code == 0
        assert "hostname" in result.output

    def test_scan_plain_file(self, runner: CliRunner, tmp_path: Path) -> None:
        plain_file = tmp_path / "plain.txt"
        plain_file.write_text("just some text\n")
        result = runner.invoke(main, ["template", "scan", str(plain_file)])
        assert result.exit_code == 0
        assert "No template syntax" in result.output

    def test_scan_nonexistent_file(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(main, ["template", "scan", "/nonexistent/file.conf"])
        assert result.exit_code == 1

    def test_scan_conditional_template(self, runner: CliRunner, tmp_path: Path) -> None:
        template_file = tmp_path / "app.conf"
        template_file.write_text("{% if debug %}debug=true{% endif %}")
        result = runner.invoke(main, ["template", "scan", str(template_file)])
        assert result.exit_code == 0
        assert "debug" in result.output


class TestCLITemplateRender:
    """Tests for the template render CLI command."""

    def test_render_with_context(self, runner: CliRunner, env_repo: Path, tmp_home: Path) -> None:
        template_file = tmp_home / ".config" / "render_test.conf"
        template_file.parent.mkdir(parents=True, exist_ok=True)
        template_file.write_text("host={{ hostname }}\n")
        result = runner.invoke(
            main,
            [
                "template",
                "render",
                str(template_file),
                "--context",
                "hostname=myserver",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "myserver" in result.output

    def test_render_without_dry_run(
        self, runner: CliRunner, env_repo: Path, tmp_home: Path
    ) -> None:
        template_file = tmp_home / ".config" / "write_test.conf"
        template_file.parent.mkdir(parents=True, exist_ok=True)
        template_file.write_text("name={{ name }}\n")
        result = runner.invoke(
            main,
            ["template", "render", str(template_file), "--context", "name=world"],
        )
        assert result.exit_code == 0
        assert "Rendered template" in result.output

    def test_render_invalid_context_format(
        self, runner: CliRunner, env_repo: Path, tmp_home: Path
    ) -> None:
        template_file = tmp_home / ".config" / "bad_ctx.conf"
        template_file.parent.mkdir(parents=True, exist_ok=True)
        template_file.write_text("val={{ val }}\n")
        result = runner.invoke(
            main,
            ["template", "render", str(template_file), "--context", "no_equals_sign"],
        )
        assert result.exit_code == 1

    def test_render_nonexistent_file(
        self, runner: CliRunner, env_repo: Path, tmp_home: Path
    ) -> None:
        result = runner.invoke(
            main,
            ["template", "render", "/nonexistent/file.conf", "--context", "name=test"],
        )
        assert result.exit_code == 1

    def test_render_not_initialized(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo_dir = tmp_path / "nonexist-repo"
        monkeypatch.setenv("DOTFILE_SYNC_DIR", str(repo_dir))
        template_file = tmp_path / "some_template.conf"
        template_file.write_text("val={{ val }}\n")
        result = runner.invoke(
            main,
            ["template", "render", str(template_file), "--context", "name=test"],
        )
        assert result.exit_code == 1


class TestCLIContextCommands:
    """Tests for the context CLI commands."""

    def test_context_list(self, runner: CliRunner, env_repo: Path) -> None:
        result = runner.invoke(main, ["context", "list"])
        assert result.exit_code == 0
        assert "default" in result.output

    def test_context_show(self, runner: CliRunner, env_repo: Path) -> None:
        result = runner.invoke(main, ["context", "show", "default"])
        assert result.exit_code == 0

    def test_context_show_empty(self, runner: CliRunner, env_repo: Path) -> None:
        result = runner.invoke(main, ["context", "show", "nonexistent"])
        assert result.exit_code == 0
        assert "empty" in result.output or "does not exist" in result.output

    def test_context_set(self, runner: CliRunner, env_repo: Path) -> None:
        result = runner.invoke(
            main, ["context", "set", "default", "hostname=testhost", "port=9090"]
        )
        assert result.exit_code == 0
        assert "Updated" in result.output

    def test_context_set_invalid_format(self, runner: CliRunner, env_repo: Path) -> None:
        result = runner.invoke(main, ["context", "set", "default", "no_equals"])
        assert result.exit_code == 1

    def test_context_delete(self, runner: CliRunner, env_repo: Path) -> None:
        # First set some vars
        runner.invoke(main, ["context", "set", "default", "todelete=yes"])
        # Then delete
        result = runner.invoke(main, ["context", "delete", "default", "todelete"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_context_delete_no_match(self, runner: CliRunner, env_repo: Path) -> None:
        result = runner.invoke(main, ["context", "delete", "default", "nonexistent_key"])
        assert result.exit_code == 0
        assert "No matching" in result.output

    def test_context_not_initialized(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo_dir = tmp_path / "nonexist-repo"
        monkeypatch.setenv("DOTFILE_SYNC_DIR", str(repo_dir))
        result = runner.invoke(main, ["context", "list"])
        assert result.exit_code == 1


class TestCLIProfileCommands:
    """Tests for the profile CLI commands."""

    def test_profile_activate(self, runner: CliRunner, env_repo: Path) -> None:
        result = runner.invoke(main, ["profile", "activate", "work"])
        assert result.exit_code == 0
        assert "work" in result.output

    def test_profile_deactivate(self, runner: CliRunner, env_repo: Path) -> None:
        # First activate
        runner.invoke(main, ["profile", "activate", "work"])
        result = runner.invoke(main, ["profile", "deactivate"])
        assert result.exit_code == 0
        assert "cleared" in result.output.lower()

    def test_profile_machine(self, runner: CliRunner, env_repo: Path) -> None:
        result = runner.invoke(main, ["profile", "machine", "laptop"])
        assert result.exit_code == 0
        assert "laptop" in result.output

    def test_profile_show(self, runner: CliRunner, env_repo: Path) -> None:
        # Set profile and machine first
        runner.invoke(main, ["profile", "activate", "work"])
        runner.invoke(main, ["profile", "machine", "laptop"])
        result = runner.invoke(main, ["profile", "show"])
        assert result.exit_code == 0
        assert "work" in result.output
        assert "laptop" in result.output

    def test_profile_show_empty(self, runner: CliRunner, env_repo: Path) -> None:
        result = runner.invoke(main, ["profile", "show"])
        assert result.exit_code == 0
        assert "none" in result.output.lower()

    def test_profile_not_initialized(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo_dir = tmp_path / "nonexist-repo"
        monkeypatch.setenv("DOTFILE_SYNC_DIR", str(repo_dir))
        result = runner.invoke(main, ["profile", "activate", "test"])
        assert result.exit_code == 1


class TestCLIHelpForSubgroups:
    """Tests for help output on subgroup commands."""

    def test_template_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["template", "--help"])
        assert result.exit_code == 0
        assert "scan" in result.output
        assert "render" in result.output

    def test_context_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["context", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "set" in result.output
        assert "delete" in result.output

    def test_profile_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["profile", "--help"])
        assert result.exit_code == 0
        assert "activate" in result.output
        assert "deactivate" in result.output
        assert "machine" in result.output
        assert "show" in result.output
