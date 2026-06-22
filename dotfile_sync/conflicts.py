"""Conflict detection and resolution for dotfile-sync.

Handles cases where the live file and backed-up file have both
changed since the last sync, requiring user-configurable resolution.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .errors import DotfileSyncError


class ConflictStrategy(StrEnum):
    """Strategies for resolving sync conflicts."""

    SKIP = "skip"  # Skip conflicting files
    KEEP_LOCAL = "keep_local"  # Keep the local (live) version
    KEEP_REPO = "keep_repo"  # Keep the repo (backed-up) version
    KEEP_NEWER = "keep_newer"  # Keep whichever was modified more recently
    MAKE_BACKUP = "make_backup"  # Save both versions (local gets .sync-backup)
    ABORT = "abort"  # Abort the operation on conflict


class ConflictRecord:
    """Records a single file conflict."""

    def __init__(
        self,
        file_path: str,
        local_mtime: float | None,
        repo_mtime: float | None,
        repo_path: str | None = None,
    ) -> None:
        self.file_path = file_path
        self.local_mtime = local_mtime
        self.repo_mtime = repo_mtime
        self._repo_path = repo_path

    @property
    def newer_side(self) -> str | None:
        """Determine which side is newer, or None if equal."""
        if self.local_mtime is None or self.repo_mtime is None:
            return None
        if self.local_mtime > self.repo_mtime:
            return "local"
        if self.repo_mtime > self.local_mtime:
            return "repo"
        return None

    def __repr__(self) -> str:
        return f"ConflictRecord({self.file_path!r}, newer={self.newer_side})"


class ConflictResult:
    """Result of resolving a conflict."""

    def __init__(
        self,
        conflict: ConflictRecord,
        strategy: ConflictStrategy,
        resolved_path: Path | None = None,
        backup_path: Path | None = None,
    ) -> None:
        self.conflict = conflict
        self.strategy = strategy
        self.resolved_path = resolved_path
        self.backup_path = backup_path

    @property
    def skipped(self) -> bool:
        return self.strategy == ConflictStrategy.SKIP

    @property
    def resolved(self) -> bool:
        return self.strategy != ConflictStrategy.ABORT

    def __repr__(self) -> str:
        return f"ConflictResult({self.conflict.file_path!r}, {self.strategy.value})"


class ConflictDetector:
    """Detects conflicts between live files and backed-up versions."""

    def __init__(self, files_dir: Path) -> None:
        self.files_dir = files_dir

    def detect_conflicts(
        self,
        manifest_entries: list[dict[str, Any]],
    ) -> list[ConflictRecord]:
        """Scan manifest entries for conflicts.

        A conflict exists when both the local file and repo copy have
        been modified since the last backup.

        Args:
            manifest_entries: List of manifest file entries.

        Returns:
            List of conflict records.
        """
        conflicts: list[ConflictRecord] = []

        for entry in manifest_entries:
            original = Path(entry["original_path"])
            repo_path = self.files_dir / entry["repo_path"]

            if not original.exists() or not repo_path.exists():
                continue

            # Skip template files for conflict detection (they get re-rendered)
            if entry.get("is_template"):
                continue

            local_mtime = self._safe_mtime(original)
            repo_mtime = self._safe_mtime(repo_path)

            # Conflict: both sides modified (local newer than repo = both changed)
            if (
                local_mtime is not None
                and repo_mtime is not None
                and local_mtime > repo_mtime
                and self._content_differs(original, repo_path)
            ):
                conflicts.append(
                    ConflictRecord(
                        file_path=entry["original_path"],
                        local_mtime=local_mtime,
                        repo_mtime=repo_mtime,
                        repo_path=entry["repo_path"],
                    )
                )

        return conflicts

    @staticmethod
    def _safe_mtime(path: Path) -> float | None:
        """Get modification time, or None if unavailable."""
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    @staticmethod
    def _content_differs(local: Path, repo: Path) -> bool:
        """Check if file contents differ."""
        try:
            return local.read_bytes() != repo.read_bytes()
        except OSError:
            return True


class ConflictResolver:
    """Resolves detected conflicts using configurable strategies."""

    def __init__(self, strategy: ConflictStrategy = ConflictStrategy.MAKE_BACKUP) -> None:
        self.strategy = strategy

    def resolve(
        self,
        conflict: ConflictRecord,
        files_dir: Path,
    ) -> ConflictResult:
        """Resolve a single conflict.

        Args:
            conflict: The conflict to resolve.
            files_dir: Path to the repo files directory.

        Returns:
            ConflictResult with resolution details.
        """
        local_path = Path(conflict.file_path)
        repo_path = files_dir / self._entry_repo_path(conflict)

        if self.strategy == ConflictStrategy.SKIP:
            return ConflictResult(conflict, self.strategy)

        if self.strategy == ConflictStrategy.KEEP_LOCAL:
            return ConflictResult(conflict, self.strategy, resolved_path=local_path)

        if self.strategy == ConflictStrategy.KEEP_REPO:
            return ConflictResult(conflict, self.strategy, resolved_path=repo_path)

        if self.strategy == ConflictStrategy.KEEP_NEWER:
            newer = conflict.newer_side
            chosen = local_path if newer == "local" else repo_path
            return ConflictResult(conflict, self.strategy, resolved_path=chosen)

        if self.strategy == ConflictStrategy.MAKE_BACKUP:
            backup_path = self._create_backup(local_path)
            return ConflictResult(
                conflict,
                self.strategy,
                resolved_path=local_path,
                backup_path=backup_path,
            )

        if self.strategy == ConflictStrategy.ABORT:
            raise DotfileSyncError(
                f"Conflict detected for {conflict.file_path}. "
                f"Both local and repo versions have changed."
            )

        return ConflictResult(conflict, ConflictStrategy.SKIP)

    def _entry_repo_path(self, conflict: ConflictRecord) -> str:
        """Get the repo path from the conflict record.

        Uses the repo_path stored in the conflict record (from manifest).
        Falls back to a safe derived path if not available.
        """
        if conflict._repo_path:
            return conflict._repo_path
        # Fallback: derive from file path, but handle non-home paths gracefully
        try:
            return str(Path(conflict.file_path).relative_to(Path.home())).replace("/", "_")
        except (ValueError, OSError):
            # Path is not under home directory; use a safe hash-like name
            return conflict.file_path.replace("/", "_").lstrip("_")

    @staticmethod
    def _create_backup(local_path: Path) -> Path:
        """Create a backup of the local file before overwrite."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = local_path.with_suffix(f".sync-backup-{timestamp}{local_path.suffix}")
        try:
            shutil.copy2(local_path, backup_path)
        except OSError as exc:
            raise DotfileSyncError(f"Failed to create backup of {local_path}: {exc}") from exc
        return backup_path

    def resolve_all(
        self,
        conflicts: list[ConflictRecord],
        files_dir: Path,
    ) -> list[ConflictResult]:
        """Resolve multiple conflicts.

        Args:
            conflicts: List of conflicts to resolve.
            files_dir: Path to the repo files directory.

        Returns:
            List of resolution results.
        """
        return [self.resolve(c, files_dir) for c in conflicts]


def generate_conflict_report(
    conflicts: list[ConflictRecord],
    results: list[ConflictResult],
) -> str:
    """Generate a human-readable conflict report.

    Args:
        conflicts: The detected conflicts.
        results: The resolution results.

    Returns:
        Formatted report string.
    """
    if not conflicts:
        return "No conflicts detected."

    lines = [f"Conflicts detected: {len(conflicts)}", ""]

    for conflict, result in zip(conflicts, results, strict=True):
        newer = conflict.newer_side or "equal"
        lines.append(f"  {conflict.file_path}")
        lines.append(f"    Strategy: {result.strategy.value}")
        lines.append(f"    Newer: {newer}")
        if result.backup_path:
            lines.append(f"    Backup: {result.backup_path}")
        if result.skipped:
            lines.append("    Action: skipped")
        lines.append("")

    return "\n".join(lines)
