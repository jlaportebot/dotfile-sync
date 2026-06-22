"""Tests for conflict detection and resolution."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from dotfile_sync.conflicts import (
    ConflictDetector,
    ConflictRecord,
    ConflictResolver,
    ConflictStrategy,
    generate_conflict_report,
)
from dotfile_sync.errors import DotfileSyncError


class TestConflictStrategy:
    """Tests for the ConflictStrategy enum."""

    def test_all_strategies(self) -> None:
        assert ConflictStrategy.SKIP.value == "skip"
        assert ConflictStrategy.KEEP_LOCAL.value == "keep_local"
        assert ConflictStrategy.KEEP_REPO.value == "keep_repo"
        assert ConflictStrategy.KEEP_NEWER.value == "keep_newer"
        assert ConflictStrategy.MAKE_BACKUP.value == "make_backup"
        assert ConflictStrategy.ABORT.value == "abort"

    def test_string_enum(self) -> None:
        assert ConflictStrategy("skip") == ConflictStrategy.SKIP


class TestConflictRecord:
    """Tests for ConflictRecord."""

    def test_newer_local(self) -> None:
        record = ConflictRecord("/home/test/.bashrc", 1000.0, 900.0)
        assert record.newer_side == "local"

    def test_newer_repo(self) -> None:
        record = ConflictRecord("/home/test/.bashrc", 900.0, 1000.0)
        assert record.newer_side == "repo"

    def test_equal_times(self) -> None:
        record = ConflictRecord("/home/test/.bashrc", 1000.0, 1000.0)
        assert record.newer_side is None

    def test_none_times(self) -> None:
        record = ConflictRecord("/home/test/.bashrc", None, None)
        assert record.newer_side is None

    def test_repr(self) -> None:
        record = ConflictRecord("/home/test/.bashrc", 1000.0, 900.0)
        assert "local" in repr(record)


class TestConflictDetector:
    """Tests for ConflictDetector."""

    def test_detect_no_conflicts(self, tmp_path: Path) -> None:
        files_dir = tmp_path / "files"
        files_dir.mkdir()
        detector = ConflictDetector(files_dir)

        # File exists only locally
        entries = [{"original_path": str(tmp_path / "local_only"), "repo_path": "local_only"}]
        (tmp_path / "local_only").write_text("content")
        # Repo file doesn't exist
        conflicts = detector.detect_conflicts(entries)
        assert len(conflicts) == 0

    def test_detect_content_conflict(self, tmp_path: Path) -> None:
        files_dir = tmp_path / "files"
        files_dir.mkdir()
        detector = ConflictDetector(files_dir)

        local_file = tmp_path / "testfile"
        local_file.write_text("local version")
        repo_file = files_dir / "testfile"
        repo_file.write_text("repo version")

        # Make local file newer
        os.utime(local_file, (time.time() + 100, time.time() + 100))

        entries = [{"original_path": str(local_file), "repo_path": "testfile"}]
        conflicts = detector.detect_conflicts(entries)
        assert len(conflicts) == 1
        assert conflicts[0].file_path == str(local_file)

    def test_skip_template_files(self, tmp_path: Path) -> None:
        files_dir = tmp_path / "files"
        files_dir.mkdir()
        detector = ConflictDetector(files_dir)

        local_file = tmp_path / "template_file"
        local_file.write_text("{{ variable }}")
        repo_file = files_dir / "template_file"
        repo_file.write_text("rendered content")

        os.utime(local_file, (time.time() + 100, time.time() + 100))

        entries = [
            {
                "original_path": str(local_file),
                "repo_path": "template_file",
                "is_template": True,
            }
        ]
        conflicts = detector.detect_conflicts(entries)
        # Templates should be skipped
        assert len(conflicts) == 0

    def test_identical_content_no_conflict(self, tmp_path: Path) -> None:
        files_dir = tmp_path / "files"
        files_dir.mkdir()
        detector = ConflictDetector(files_dir)

        local_file = tmp_path / "same_content"
        local_file.write_text("same content")
        repo_file = files_dir / "same_content"
        repo_file.write_text("same content")

        # Make local newer but content is same
        os.utime(local_file, (time.time() + 100, time.time() + 100))

        entries = [{"original_path": str(local_file), "repo_path": "same_content"}]
        conflicts = detector.detect_conflicts(entries)
        assert len(conflicts) == 0


class TestConflictResolver:
    """Tests for ConflictResolver."""

    def test_skip_strategy(self) -> None:
        resolver = ConflictResolver(ConflictStrategy.SKIP)
        conflict = ConflictRecord("/home/test/.bashrc", 100.0, 50.0)
        result = resolver.resolve(conflict, Path("/repo/files"))
        assert result.skipped

    def test_keep_local_strategy(self) -> None:
        resolver = ConflictResolver(ConflictStrategy.KEEP_LOCAL)
        conflict = ConflictRecord("/home/test/.bashrc", 100.0, 50.0)
        result = resolver.resolve(conflict, Path("/repo/files"))
        assert result.resolved
        assert "bashrc" in str(result.resolved_path)

    def test_keep_repo_strategy(self) -> None:
        resolver = ConflictResolver(ConflictStrategy.KEEP_REPO)
        conflict = ConflictRecord("/home/test/.bashrc", 100.0, 50.0)
        result = resolver.resolve(conflict, Path("/repo/files"))
        assert result.resolved

    def test_keep_newer_local(self) -> None:
        resolver = ConflictResolver(ConflictStrategy.KEEP_NEWER)
        conflict = ConflictRecord("/home/test/.bashrc", 100.0, 50.0)
        result = resolver.resolve(conflict, Path("/repo/files"))
        assert result.resolved

    def test_keep_newer_repo(self) -> None:
        resolver = ConflictResolver(ConflictStrategy.KEEP_NEWER)
        conflict = ConflictRecord("/home/test/.bashrc", 50.0, 100.0)
        result = resolver.resolve(conflict, Path("/repo/files"))
        assert result.resolved

    def test_abort_strategy(self) -> None:
        resolver = ConflictResolver(ConflictStrategy.ABORT)
        conflict = ConflictRecord("/home/test/.bashrc", 100.0, 50.0)
        with pytest.raises(DotfileSyncError, match="Conflict detected"):
            resolver.resolve(conflict, Path("/repo/files"))

    def test_make_backup_strategy(self, tmp_path: Path) -> None:
        resolver = ConflictResolver(ConflictStrategy.MAKE_BACKUP)
        # Create a real local file to back up
        local_file = tmp_path / "test.conf"
        local_file.write_text("local config")
        conflict = ConflictRecord(str(local_file), 100.0, 50.0)

        result = resolver.resolve(conflict, tmp_path / "files")
        assert result.resolved
        assert result.backup_path is not None
        assert result.backup_path.exists()
        # Backup should contain the original content
        assert result.backup_path.read_text() == "local config"

    def test_resolve_all(self) -> None:
        resolver = ConflictResolver(ConflictStrategy.SKIP)
        conflicts = [
            ConflictRecord("/home/a", 100.0, 50.0),
            ConflictRecord("/home/b", 50.0, 100.0),
        ]
        results = resolver.resolve_all(conflicts, Path("/repo/files"))
        assert len(results) == 2
        assert all(r.skipped for r in results)


class TestGenerateConflictReport:
    """Tests for the conflict report generator."""

    def test_no_conflicts(self) -> None:
        report = generate_conflict_report([], [])
        assert "No conflicts" in report

    def test_with_conflicts(self) -> None:
        conflicts = [ConflictRecord("/home/test/.bashrc", 100.0, 50.0)]
        results = [ConflictResolver(ConflictStrategy.SKIP).resolve(conflicts[0], Path("/repo"))]
        report = generate_conflict_report(conflicts, results)
        assert "1" in report
        assert "skip" in report
        assert ".bashrc" in report

    def test_report_with_backup(self, tmp_path: Path) -> None:
        local_file = tmp_path / "test.conf"
        local_file.write_text("content")
        conflicts = [ConflictRecord(str(local_file), 100.0, 50.0)]
        results = [ConflictResolver(ConflictStrategy.MAKE_BACKUP).resolve(conflicts[0], tmp_path)]
        report = generate_conflict_report(conflicts, results)
        assert "make_backup" in report
