"""Tests for the hook system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dotfile_sync.errors import DotfileSyncError
from dotfile_sync.hooks import (
    HookConfig,
    HookEvent,
    HookResult,
    HookRunner,
    create_hook_config,
    create_hook_runner,
)


class TestHookEvent:
    """Tests for the HookEvent enum."""

    def test_event_values(self) -> None:
        assert HookEvent.PRE_BACKUP.value == "pre_backup"
        assert HookEvent.POST_BACKUP.value == "post_backup"
        assert HookEvent.PRE_RESTORE.value == "pre_restore"
        assert HookEvent.POST_RESTORE.value == "post_restore"
        assert HookEvent.PRE_TRACK.value == "pre_track"
        assert HookEvent.POST_TRACK.value == "post_track"

    def test_string_enum(self) -> None:
        assert HookEvent("pre_backup") == HookEvent.PRE_BACKUP


class TestHookResult:
    """Tests for the HookResult class."""

    def test_success(self) -> None:
        result = HookResult(
            event=HookEvent.PRE_BACKUP,
            command="echo hello",
            exit_code=0,
            stdout="hello\n",
            stderr="",
        )
        assert result.success

    def test_failure(self) -> None:
        result = HookResult(
            event=HookEvent.PRE_BACKUP,
            command="false",
            exit_code=1,
            stdout="",
            stderr="error",
        )
        assert not result.success

    def test_repr_success(self) -> None:
        result = HookResult(
            event=HookEvent.PRE_BACKUP,
            command="echo test",
            exit_code=0,
            stdout="test\n",
            stderr="",
        )
        assert "ok" in repr(result)

    def test_repr_failure(self) -> None:
        result = HookResult(
            event=HookEvent.PRE_BACKUP,
            command="false",
            exit_code=127,
            stdout="",
            stderr="not found",
        )
        assert "exit(127)" in repr(result)


class TestHookConfig:
    """Tests for the HookConfig class."""

    def test_empty_config(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        assert config.get_hooks(HookEvent.PRE_BACKUP) == []

    def test_add_hook(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "echo pre-backup")
        assert config.get_hooks(HookEvent.PRE_BACKUP) == ["echo pre-backup"]

    def test_multiple_hooks(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "echo first")
        config.add_hook(HookEvent.PRE_BACKUP, "echo second")
        hooks = config.get_hooks(HookEvent.PRE_BACKUP)
        assert len(hooks) == 2
        assert hooks[0] == "echo first"
        assert hooks[1] == "echo second"

    def test_remove_hook(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "echo first")
        config.add_hook(HookEvent.PRE_BACKUP, "echo second")
        assert config.remove_hook(HookEvent.PRE_BACKUP, 0)
        assert config.get_hooks(HookEvent.PRE_BACKUP) == ["echo second"]

    def test_remove_hook_invalid_index(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "echo first")
        assert not config.remove_hook(HookEvent.PRE_BACKUP, 5)

    def test_clear_hooks_for_event(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "echo pre")
        config.add_hook(HookEvent.POST_BACKUP, "echo post")
        config.clear_hooks(HookEvent.PRE_BACKUP)
        assert config.get_hooks(HookEvent.PRE_BACKUP) == []
        assert len(config.get_hooks(HookEvent.POST_BACKUP)) == 1

    def test_clear_all_hooks(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "echo pre")
        config.add_hook(HookEvent.POST_BACKUP, "echo post")
        config.clear_hooks()
        assert config.get_hooks(HookEvent.PRE_BACKUP) == []
        assert config.get_hooks(HookEvent.POST_BACKUP) == []

    def test_persistence(self, tmp_path: Path) -> None:
        hooks_path = tmp_path / "hooks.json"
        config = HookConfig(hooks_path)
        config.add_hook(HookEvent.PRE_BACKUP, "echo persist")
        # Reload from disk
        config2 = HookConfig(hooks_path)
        assert config2.get_hooks(HookEvent.PRE_BACKUP) == ["echo persist"]

    def test_list_all(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "echo pre")
        config.add_hook(HookEvent.POST_BACKUP, "echo post")
        all_hooks = config.list_all()
        assert "pre_backup" in all_hooks
        assert "post_backup" in all_hooks

    def test_load_corrupt_file(self, tmp_path: Path) -> None:
        hooks_path = tmp_path / "hooks.json"
        hooks_path.write_text("not valid json {{{")
        config = HookConfig(hooks_path)
        # Should not raise, just use empty hooks
        assert config.get_hooks(HookEvent.PRE_BACKUP) == []


class TestHookRunner:
    """Tests for the HookRunner class."""

    def test_run_success_hook(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "echo hello")
        runner = HookRunner(config, working_dir=tmp_path)
        results = runner.run_hooks(HookEvent.PRE_BACKUP)
        assert len(results) == 1
        assert results[0].success
        assert "hello" in results[0].stdout

    def test_run_failing_hook_abort(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "exit 1")
        runner = HookRunner(config, working_dir=tmp_path)
        with pytest.raises(DotfileSyncError, match="Hook for pre_backup failed"):
            runner.run_hooks(HookEvent.PRE_BACKUP, abort_on_failure=True)

    def test_run_failing_hook_continue(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "exit 1")
        config.add_hook(HookEvent.PRE_BACKUP, "echo still-runs")
        runner = HookRunner(config, working_dir=tmp_path)
        results = runner.run_hooks(HookEvent.PRE_BACKUP, abort_on_failure=False)
        assert len(results) == 2
        assert not results[0].success
        assert results[1].success

    def test_run_no_hooks(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        runner = HookRunner(config, working_dir=tmp_path)
        results = runner.run_hooks(HookEvent.PRE_BACKUP)
        assert results == []

    def test_run_with_env(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "echo $DOTFILE_SYNC_HOOK_EVENT")
        runner = HookRunner(config, working_dir=tmp_path)
        results = runner.run_hooks(HookEvent.PRE_BACKUP)
        assert len(results) == 1
        assert "pre_backup" in results[0].stdout

    def test_run_custom_env(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        config.add_hook(HookEvent.PRE_BACKUP, "echo $MY_CUSTOM_VAR")
        runner = HookRunner(config, working_dir=tmp_path)
        results = runner.run_hooks(HookEvent.PRE_BACKUP, env={"MY_CUSTOM_VAR": "custom_value"})
        assert len(results) == 1
        assert "custom_value" in results[0].stdout

    def test_hook_timeout(self, tmp_path: Path) -> None:
        config = HookConfig(tmp_path / "hooks.json")
        # Use a short sleep that will exceed the test timeout
        config.add_hook(HookEvent.PRE_BACKUP, "sleep 10")
        runner = HookRunner(config, working_dir=tmp_path, hook_timeout=1)
        results = runner.run_hooks(HookEvent.PRE_BACKUP, abort_on_failure=False)
        assert len(results) == 1
        assert results[0].exit_code == 124
        assert "timed out" in results[0].stderr.lower()


class TestCreateHookConfig:
    """Tests for factory functions."""

    def test_creates_config(self, tmp_path: Path) -> None:
        config = create_hook_config(tmp_path)
        assert isinstance(config, HookConfig)

    def test_creates_runner(self, tmp_path: Path) -> None:
        runner = create_hook_runner(tmp_path)
        assert isinstance(runner, HookRunner)
        assert runner.working_dir == tmp_path
