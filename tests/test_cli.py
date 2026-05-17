"""Tests for the CLI interface."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from dotfile_sync.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCLIVersion:
    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "dotfile-sync" in result.output


class TestCLIHelp:
    def test_main_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "dotfile-sync" in result.output
        # Check all commands are registered
        assert "init" in result.output
        assert "track" in result.output
        assert "backup" in result.output
        assert "restore" in result.output
        assert "diff" in result.output
        assert "status" in result.output
        assert "push" in result.output
        assert "pull" in result.output
        assert "list" in result.output
        assert "untrack" in result.output

    def test_init_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert "--remote" in result.output

    def test_track_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["track", "--help"])
        assert result.exit_code == 0
        assert "PATH" in result.output

    def test_backup_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["backup", "--help"])
        assert result.exit_code == 0
        assert "--message" in result.output

    def test_restore_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["restore", "--help"])
        assert result.exit_code == 0
        assert "--only" in result.output

    def test_untrack_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["untrack", "--help"])
        assert result.exit_code == 0
        assert "PATH" in result.output

    def test_diff_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["diff", "--help"])
        assert result.exit_code == 0

    def test_status_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["status", "--help"])
        assert result.exit_code == 0

    def test_push_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["push", "--help"])
        assert result.exit_code == 0

    def test_pull_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["pull", "--help"])
        assert result.exit_code == 0
