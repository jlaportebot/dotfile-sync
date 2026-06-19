"""Core logic for dotfile-sync: manifest management, backup, restore, diff."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from git import Repo

# Default location for the dotfile-sync repository
DEFAULT_REPO_DIR = Path.home() / ".dotfile-sync"
MANIFEST_FILE = "manifest.json"
FILES_DIR = "files"


class DotfileSyncError(Exception):
    """Base exception for dotfile-sync errors."""


class NotInitializedError(DotfileSyncError):
    """Raised when the dotfile-sync repo has not been initialized."""


class Manifest:
    """Manages the manifest.json file that tracks dotfiles."""

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.manifest_path.exists():
            with Path(self.manifest_path).open() as f:
                self._data = json.load(f)
        else:
            self._data = {"version": "1.0", "files": []}

    def save(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with Path(self.manifest_path).open("w") as f:
            json.dump(self._data, f, indent=2)
            f.write("\n")

    @property
    def files(self) -> list[dict[str, str]]:
        return cast(list[dict[str, str]], self._data.get("files", []))

    def add_file(self, original_path: str, repo_path: str) -> None:
        """Add a file to the manifest."""
        # Check if already tracked
        for entry in self.files:
            if entry["original_path"] == original_path:
                return  # Already tracked
        self._data["files"].append({
            "original_path": original_path,
            "repo_path": repo_path,
            "added_at": datetime.now(UTC).isoformat(),
        })
        self.save()

    def remove_file(self, original_path: str) -> bool:
        """Remove a file from the manifest. Returns True if it was found."""
        before = len(self._data["files"])
        self._data["files"] = [
            f for f in self._data["files"] if f["original_path"] != original_path
        ]
        if len(self._data["files"]) < before:
            self.save()
            return True
        return False

    def get_entry(self, original_path: str) -> dict[str, str] | None:
        """Get a manifest entry by original path."""
        for entry in self.files:
            if entry["original_path"] == original_path:
                return entry
        return None

    def is_tracked(self, original_path: str) -> bool:
        return self.get_entry(original_path) is not None


class DotfileSync:
    """Main class for dotfile-sync operations."""

    def __init__(self, repo_dir: Path | None = None) -> None:
        self.repo_dir = repo_dir or DEFAULT_REPO_DIR
        self.manifest_path = self.repo_dir / MANIFEST_FILE
        self.files_dir = self.repo_dir / FILES_DIR

    def _ensure_initialized(self) -> None:
        """Raise NotInitializedError if the repo hasn't been initialized."""
        if not self.repo_dir.exists() or not (self.repo_dir / ".git").exists():
            raise NotInitializedError(
                "dotfile-sync is not initialized. Run `dotfile-sync init` first."
            )

    def _get_repo(self) -> Repo:
        """Get the GitPython Repo object."""
        return Repo(str(self.repo_dir))

    def init(self, remote_url: str | None = None) -> str:
        """Initialize the dotfile-sync repository."""
        if self.repo_dir.exists():
            return f"Repository already exists at {self.repo_dir}"

        # Create directory structure
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)

        # Initialize manifest
        manifest = Manifest(self.manifest_path)
        manifest.save()

        # Initialize git repo
        repo = Repo.init(str(self.repo_dir))

        # Optionally add remote
        if remote_url:
            repo.create_remote("origin", remote_url)

        # Initial commit
        repo.index.add([MANIFEST_FILE])
        repo.index.commit("chore: initialize dotfile-sync repository")

        return f"Initialized dotfile-sync repository at {self.repo_dir}"

    def track(self, path: str) -> str:
        """Add a file or directory to the tracking manifest."""
        self._ensure_initialized()
        source = Path(path).expanduser().resolve()

        if not source.exists():
            raise DotfileSyncError(f"Path does not exist: {source}")

        manifest = Manifest(self.manifest_path)

        if source.is_dir():
            # Track all files in the directory recursively
            added = 0
            for file_path in sorted(source.rglob("*")):
                if file_path.is_file():
                    rel = file_path.relative_to(Path.home())
                    repo_path = str(rel).replace(os.sep, "/")
                    # Dots in filenames become underscores prefixed with _
                    # to avoid hidden file issues
                    repo_path = _encode_repo_path(repo_path)
                    manifest.add_file(str(file_path), repo_path)
                    added += 1
            return f"Tracking {added} file(s) from {source}"
        else:
            rel = source.relative_to(Path.home())
            repo_path = str(rel).replace(os.sep, "/")
            repo_path = _encode_repo_path(repo_path)
            if manifest.is_tracked(str(source)):
                return f"Already tracking: {source}"
            manifest.add_file(str(source), repo_path)
            return f"Now tracking: {source}"

    def untrack(self, path: str) -> str:
        """Remove a file or directory from the tracking manifest."""
        self._ensure_initialized()
        source = Path(path).expanduser().resolve()
        manifest = Manifest(self.manifest_path)

        if source.is_dir():
            removed = 0
            entries_to_remove = [
                e["original_path"]
                for e in manifest.files
                if e["original_path"].startswith(str(source))
            ]
            for entry_path in entries_to_remove:
                if manifest.remove_file(entry_path):
                    removed += 1
            return f"Stopped tracking {removed} file(s) from {source}"
        else:
            if manifest.remove_file(str(source)):
                return f"Stopped tracking: {source}"
            return f"Not currently tracked: {source}"

    def backup(self, message: str | None = None) -> str:
        """Copy all tracked files into the repo and commit."""
        self._ensure_initialized()
        manifest = Manifest(self.manifest_path)
        repo = self._get_repo()

        if not manifest.files:
            return "No files tracked. Use `dotfile-sync track <path>` to add files."

        backed_up = 0
        for entry in manifest.files:
            original = Path(entry["original_path"])
            repo_path = self.files_dir / entry["repo_path"]

            if original.exists():
                repo_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, repo_path)
                backed_up += 1

        if backed_up == 0:
            return "No tracked files found on disk. Nothing to back up."

        # Stage and commit
        repo.index.add([str(self.files_dir)])
        repo.index.add([str(self.manifest_path)])

        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        commit_msg = message or f"backup: {backed_up} file(s) at {timestamp}"
        repo.index.commit(commit_msg)

        return f"Backed up {backed_up} file(s). Committed as: {commit_msg}"

    def restore(self, only: str | None = None) -> str:
        """Copy files from the repo back to their original locations."""
        self._ensure_initialized()
        manifest = Manifest(self.manifest_path)

        if not manifest.files:
            return "No files in manifest. Nothing to restore."

        restored = 0
        skipped = 0
        for entry in manifest.files:
            if only and entry["original_path"] != only:
                continue

            original = Path(entry["original_path"])
            repo_path = self.files_dir / entry["repo_path"]

            if not repo_path.exists():
                skipped += 1
                continue

            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_path, original)
            restored += 1

        msg = f"Restored {restored} file(s)"
        if skipped:
            msg += f", skipped {skipped} (not found in repo)"
        return msg

    def diff(self) -> str:
        """Show differences between live files and the last backup."""
        self._ensure_initialized()
        manifest = Manifest(self.manifest_path)

        if not manifest.files:
            return "No files tracked. Nothing to diff."

        results = []
        for entry in manifest.files:
            original = Path(entry["original_path"])
            repo_path = self.files_dir / entry["repo_path"]

            if not original.exists() and not repo_path.exists():
                continue

            if original.exists() and not repo_path.exists():
                results.append(f"  {entry['original_path']}: NEW (not yet backed up)")
                continue

            if not original.exists() and repo_path.exists():
                results.append(f"  {entry['original_path']}: DELETED on disk")
                continue

            # Compare file contents
            orig_content = original.read_bytes()
            repo_content = repo_path.read_bytes()
            if orig_content != repo_content:
                results.append(f"  {entry['original_path']}: MODIFIED")
            else:
                results.append(f"  {entry['original_path']}: up to date")

        if not results:
            return "All tracked files are up to date."

        return "Status of tracked files:\n" + "\n".join(results)

    def status(self) -> str:
        """Show which tracked files have been modified since last backup."""
        return self.diff()

    def list_tracked(self) -> str:
        """List all tracked files."""
        self._ensure_initialized()
        manifest = Manifest(self.manifest_path)

        if not manifest.files:
            return "No files tracked. Use `dotfile-sync track <path>` to add files."

        lines = ["Tracked files:"]
        for entry in manifest.files:
            original = Path(entry["original_path"])
            repo_path = self.files_dir / entry["repo_path"]
            exists_on_disk = "✓" if original.exists() else "✗"
            backed_up = "✓" if repo_path.exists() else "✗"
            lines.append(f"  [{exists_on_disk}] [{backed_up}] {entry['original_path']}")

        lines.append("")
        lines.append("  [on disk] [backed up]  path")
        return "\n".join(lines)

    def push(self) -> str:
        """Push the backup repo to its remote."""
        self._ensure_initialized()
        repo = self._get_repo()

        if "origin" not in [r.name for r in repo.remotes]:
            raise DotfileSyncError(
                "No remote configured. Add one with: "
                "cd ~/.dotfile-sync && git remote add origin <url>"
            )

        repo.remotes.origin.push()
        return "Pushed to remote."

    def pull(self) -> str:
        """Pull changes from the remote and restore."""
        self._ensure_initialized()
        repo = self._get_repo()

        if "origin" not in [r.name for r in repo.remotes]:
            raise DotfileSyncError(
                "No remote configured. Add one with: "
                "cd ~/.dotfile-sync && git remote add origin <url>"
            )

        repo.remotes.origin.pull()
        # After pulling, restore
        restore_msg = self.restore()
        return f"Pulled from remote. {restore_msg}"


def _encode_repo_path(rel_path: str) -> str:
    """Encode a relative path for use in the repo.

    Replaces leading dots in filenames with underscore to avoid
    hidden file issues in the backup repo, while keeping the path
    readable.
    """
    parts = rel_path.split("/")
    encoded = []
    for part in parts:
        if part.startswith("."):
            part = "_" + part[1:]
        encoded.append(part)
    return "/".join(encoded)


def _decode_repo_path(repo_path: str) -> str:
    """Decode a repo path back to the original relative path."""
    parts = repo_path.split("/")
    decoded = []
    for part in parts:
        if part.startswith("_"):
            # Only decode if the original had a dot
            part = "." + part[1:]
        decoded.append(part)
    return "/".join(decoded)
