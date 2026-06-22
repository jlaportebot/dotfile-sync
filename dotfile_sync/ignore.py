"""Ignore pattern matching for dotfile-sync.

Supports .gitignore-style patterns for excluding files from tracking
and backup operations.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath


class IgnorePattern:
    """A single ignore pattern with gitignore semantics.

    Supports:
    - Plain names: "README.md" matches any file named README.md
    - Glob patterns: "*.pyc" matches all .pyc files
    - Directory patterns: "build/" matches the build directory
    - Rooted patterns: "/tmp/" only matches tmp/ at repo root
    - Negation: "!important.pyc" un-ignores previously ignored files
    - Comments: Lines starting with # are ignored
    """

    def __init__(self, pattern: str, base_dir: Path | None = None) -> None:
        self.raw = pattern.strip()
        self.base_dir = base_dir or Path()
        self.negated = False
        self.directory_only = False
        self.rooted = False
        self._regex: re.Pattern[str] | None = None

        line = self.raw

        # Skip empty lines and comments
        if not line or line.startswith("#"):
            self._regex = re.compile(r"$^")  # matches nothing
            return

        # Handle negation
        if line.startswith("!"):
            self.negated = True
            line = line[1:]

        # Handle rooted patterns
        if line.startswith("/"):
            self.rooted = True
            line = line[1:]

        # Handle directory-only patterns
        if line.endswith("/"):
            self.directory_only = True
            line = line.rstrip("/")

        self._pattern_str = line
        self._regex = self._compile(line)

    def _compile(self, pattern: str) -> re.Pattern[str]:
        """Convert a gitignore-style pattern to a regex."""
        regex_parts: list[str] = []
        i = 0
        n = len(pattern)

        while i < n:
            c = pattern[i]

            if c == "*":
                if i + 1 < n and pattern[i + 1] == "*":
                    # Double star — match any path segment(s)
                    if i + 2 < n and pattern[i + 2] == "/":
                        regex_parts.append("(?:.+/)?")
                        i += 3
                    else:
                        regex_parts.append(".*")
                        i += 2
                else:
                    # Single star — match anything except /
                    regex_parts.append("[^/]*")
                    i += 1
            elif c == "?":
                regex_parts.append("[^/]")
                i += 1
            elif c == "[":
                # Character class
                j = i + 1
                if j < n and pattern[j] == "!":
                    j += 1
                if j < n and pattern[j] == "]":
                    j += 1
                while j < n and pattern[j] != "]":
                    j += 1
                regex_parts.append(pattern[i : j + 1].replace("\\", "\\\\"))
                i = j + 1
            elif c in r".+^${}|()":
                regex_parts.append("\\" + c)
                i += 1
            else:
                regex_parts.append(c)
                i += 1

        regex_str = "".join(regex_parts)

        if self.rooted:
            # For rooted patterns, match exactly at root
            if self.directory_only:
                # Directory patterns should match with or without trailing slash
                full_regex = f"^{regex_str}/?$"
            else:
                full_regex = f"^{regex_str}$"
        else:
            # Match at any depth
            if "/" in regex_str:
                # Pattern contains path separator - match full path
                if self.directory_only:
                    # Directory patterns: match with optional trailing slash
                    full_regex = f"(?:^|/){regex_str}/?(?:/|$)"
                else:
                    full_regex = f"(?:^|/){regex_str}(?:/|$)"
            else:
                # Simple name pattern - match at any level
                if self.directory_only:
                    full_regex = f"(?:^|/){regex_str}/?$"
                else:
                    full_regex = f"(?:^|/){regex_str}$"

        return re.compile(full_regex)

    def matches(self, path: Path, is_dir: bool = False) -> bool:
        """Check if a path matches this pattern.

        Args:
            path: The path to check (relative to base_dir).
            is_dir: Whether the path is a directory.

        Returns:
            True if the path matches the pattern.
        """
        if self._regex is None:
            return False

        if self.directory_only and not is_dir:
            return False

        # Convert to posix-style relative path string
        try:
            rel = path.relative_to(self.base_dir)
            path_str = str(PurePosixPath(rel))
        except ValueError:
            path_str = str(PurePosixPath(path))

        if is_dir:
            path_str += "/"

        result = bool(self._regex.search(path_str))
        return result

    def __repr__(self) -> str:
        flags = []
        if self.negated:
            flags.append("negated")
        if self.directory_only:
            flags.append("dir-only")
        if self.rooted:
            flags.append("rooted")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        return f"IgnorePattern({self.raw!r}{flag_str})"


class IgnoreMatcher:
    """Manages a collection of ignore patterns (like .gitignore).

    Evaluates patterns in order, with later patterns overriding earlier ones.
    """

    BUILTIN_PATTERNS = [
        ".git/",
        "__pycache__/",
        "*.pyc",
        ".DS_Store",
        "*.swp",
        "*.swo",
        "*~",
        ".dotfile-sync/",
    ]

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path()
        self._patterns: list[IgnorePattern] = []
        self._load_builtins()

    def _load_builtins(self) -> None:
        """Load built-in ignore patterns."""
        for raw in self.BUILTIN_PATTERNS:
            self._patterns.append(IgnorePattern(raw, self.base_dir))

    def add_pattern(self, pattern: str) -> None:
        """Add an ignore pattern."""
        self._patterns.append(IgnorePattern(pattern, self.base_dir))

    def add_patterns(self, patterns: list[str]) -> None:
        """Add multiple ignore patterns."""
        for p in patterns:
            self.add_pattern(p)

    def load_from_file(self, ignore_file: Path) -> None:
        """Load patterns from a .dotfileignore file.

        Args:
            ignore_file: Path to the ignore file.
        """
        if not ignore_file.exists():
            return
        try:
            content = ignore_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                self.add_pattern(line)
        except (OSError, UnicodeDecodeError):
            pass

    def is_ignored(self, path: Path, is_dir: bool = False) -> bool:
        """Check if a path should be ignored.

        Evaluates all patterns in order. The last matching pattern wins.

        Args:
            path: The path to check.
            is_dir: Whether the path is a directory.

        Returns:
            True if the path should be ignored.
        """
        ignored = False
        for pattern in self._patterns:
            if pattern.matches(path, is_dir=is_dir):
                ignored = not pattern.negated
        return ignored

    @property
    def patterns(self) -> list[IgnorePattern]:
        """Get all active patterns."""
        return list(self._patterns)

    def count(self) -> int:
        """Count non-empty, non-comment patterns."""
        return sum(1 for p in self._patterns if p.raw and not p.raw.startswith("#"))


def create_ignore_matcher(repo_dir: Path) -> IgnoreMatcher:
    """Create an ignore matcher for the given repo directory.

    Loads built-in patterns and any .dotfileignore file in the repo.

    Args:
        repo_dir: The dotfile-sync repository directory.

    Returns:
        Configured IgnoreMatcher.
    """
    matcher = IgnoreMatcher(base_dir=repo_dir)
    ignore_file = repo_dir / ".dotfileignore"
    matcher.load_from_file(ignore_file)
    return matcher
