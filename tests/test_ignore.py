"""Tests for ignore pattern matching."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dotfile_sync.ignore import IgnoreMatcher, IgnorePattern, create_ignore_matcher


class TestIgnorePattern:
    """Tests for individual ignore patterns."""

    def test_plain_filename_match(self) -> None:
        pattern = IgnorePattern("README.md")
        assert pattern.matches(Path("README.md"))
        assert pattern.matches(Path("subdir/README.md"))
        assert not pattern.matches(Path("readme.md"))

    def test_glob_star_match(self) -> None:
        pattern = IgnorePattern("*.pyc")
        assert pattern.matches(Path("foo.pyc"))
        assert pattern.matches(Path("subdir/bar.pyc"))
        assert not pattern.matches(Path("foo.py"))

    def test_directory_pattern(self) -> None:
        pattern = IgnorePattern("build/")
        assert pattern.matches(Path("build"), is_dir=True)
        assert not pattern.matches(Path("build"), is_dir=False)
        assert not pattern.matches(Path("src/build.py"), is_dir=False)

    def test_rooted_pattern(self) -> None:
        pattern = IgnorePattern("/tmp/")
        assert pattern.matches(Path("tmp"), is_dir=True)
        # Rooted patterns should not match nested paths
        assert not pattern.matches(Path("subdir/tmp"), is_dir=True)

    def test_negation_pattern(self) -> None:
        pattern = IgnorePattern("!important.pyc")
        assert pattern.negated is True
        assert pattern.matches(Path("important.pyc"))

    def test_comment_line(self) -> None:
        pattern = IgnorePattern("# this is a comment")
        assert not pattern.matches(Path("anything"))

    def test_empty_line(self) -> None:
        pattern = IgnorePattern("")
        assert not pattern.matches(Path("anything"))

    def test_double_star_pattern(self) -> None:
        pattern = IgnorePattern("**/logs")
        assert pattern.matches(Path("logs"), is_dir=True)
        assert pattern.matches(Path("subdir/logs"), is_dir=True)

    def test_wildcard_question_mark(self) -> None:
        pattern = IgnorePattern("file?.txt")
        assert pattern.matches(Path("file1.txt"))
        assert pattern.matches(Path("fileA.txt"))
        assert not pattern.matches(Path("file12.txt"))

    def test_repr(self) -> None:
        pattern = IgnorePattern("build/")
        assert "build/" in repr(pattern)
        assert "dir-only" in repr(pattern)

    def test_negated_repr(self) -> None:
        pattern = IgnorePattern("!keep.me")
        assert "negated" in repr(pattern)


class TestIgnoreMatcher:
    """Tests for the IgnoreMatcher collection."""

    def test_builtin_patterns(self) -> None:
        matcher = IgnoreMatcher()
        assert matcher.is_ignored(Path("__pycache__"), is_dir=True)
        assert matcher.is_ignored(Path("foo.pyc"))
        assert matcher.is_ignored(Path(".DS_Store"))

    def test_add_pattern(self) -> None:
        matcher = IgnoreMatcher()
        matcher.add_pattern("custom_ignore/")
        assert matcher.is_ignored(Path("custom_ignore"), is_dir=True)

    def test_add_patterns_list(self) -> None:
        matcher = IgnoreMatcher()
        matcher.add_patterns(["*.log", "temp/"])
        assert matcher.is_ignored(Path("debug.log"))
        assert matcher.is_ignored(Path("temp"), is_dir=True)

    def test_negation_overrides(self) -> None:
        matcher = IgnoreMatcher()
        matcher.add_pattern("*.log")
        assert matcher.is_ignored(Path("important.log"))
        matcher.add_pattern("!important.log")
        assert not matcher.is_ignored(Path("important.log"))
        # Other log files still ignored
        assert matcher.is_ignored(Path("debug.log"))

    def test_load_from_file(self, tmp_path: Path) -> None:
        ignore_file = tmp_path / ".dotfileignore"
        ignore_file.write_text("*.tmp\n# comment\ncache/\n")
        matcher = IgnoreMatcher(base_dir=tmp_path)
        matcher.load_from_file(ignore_file)
        assert matcher.is_ignored(Path("test.tmp"))
        assert matcher.is_ignored(Path("cache"), is_dir=True)

    def test_load_missing_file(self, tmp_path: Path) -> None:
        matcher = IgnoreMatcher(base_dir=tmp_path)
        # Should not raise
        matcher.load_from_file(tmp_path / "nonexistent")

    def test_count(self) -> None:
        matcher = IgnoreMatcher()
        initial = matcher.count()
        matcher.add_pattern("custom/")
        assert matcher.count() == initial + 1

    def test_patterns_property(self) -> None:
        matcher = IgnoreMatcher()
        patterns = matcher.patterns
        assert len(patterns) > 0

    def test_git_dir_ignored(self) -> None:
        matcher = IgnoreMatcher()
        assert matcher.is_ignored(Path(".git"), is_dir=True)

    def test_dotfile_sync_dir_ignored(self) -> None:
        matcher = IgnoreMatcher()
        assert matcher.is_ignored(Path(".dotfile-sync"), is_dir=True)

    def test_non_ignored_file(self) -> None:
        matcher = IgnoreMatcher()
        assert not matcher.is_ignored(Path("config.yaml"))
        assert not matcher.is_ignored(Path("settings.json"))


class TestCreateIgnoreMatcher:
    """Tests for the factory function."""

    def test_creates_matcher_with_file(self, tmp_path: Path) -> None:
        ignore_file = tmp_path / ".dotfileignore"
        ignore_file.write_text("test_pattern/\n")
        matcher = create_ignore_matcher(tmp_path)
        assert isinstance(matcher, IgnoreMatcher)
        assert matcher.is_ignored(Path("test_pattern"), is_dir=True)

    def test_creates_matcher_without_file(self, tmp_path: Path) -> None:
        matcher = create_ignore_matcher(tmp_path)
        assert isinstance(matcher, IgnoreMatcher)
        # Built-in patterns should still work
        assert matcher.is_ignored(Path("__pycache__"), is_dir=True)
