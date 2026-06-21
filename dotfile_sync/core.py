"""Core logic for dotfile-sync: manifest management, backup, restore, diff."""

from __future__ import annotations

import difflib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from git import Repo

from .errors import DotfileSyncError, NotInitializedError
from .templates import (
    ContextManager,
    TemplateEngine,
    TemplateRenderError,
    create_context_manager,
    create_template_engine,
)

# Default location for the dotfile-sync repository
DEFAULT_REPO_DIR = Path.home() / ".dotfile-sync"
MANIFEST_FILE = "manifest.json"
FILES_DIR = "files"
TEMPLATES_DIR = "templates"
CONTEXTS_DIR = "contexts"


def _get_repo_dir() -> Path:
    """Get the repo directory from env or default."""
    env_dir = os.environ.get("DOTFILE_SYNC_DIR")
    if env_dir:
        return Path(env_dir)
    return DEFAULT_REPO_DIR


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
    def files(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._data.get("files", []))

    @property
    def active_profile(self) -> str | None:
        """Get the currently active profile name."""
        return self._data.get("active_profile")

    @active_profile.setter
    def active_profile(self, name: str | None) -> None:
        """Set the active profile."""
        self._data["active_profile"] = name
        self.save()

    @property
    def machine_name(self) -> str | None:
        """Get the machine name for template rendering."""
        return self._data.get("machine_name")

    @machine_name.setter
    def machine_name(self, name: str | None) -> None:
        """Set the machine name."""
        self._data["machine_name"] = name
        self.save()

    def add_file(self, original_path: str, repo_path: str, *, is_template: bool = False) -> None:
        """Add a file to the manifest.

        Args:
            original_path: Absolute path to the original file.
            repo_path: Relative path within the backup repo.
            is_template: Whether this file is managed as a template.
        """
        for entry in self.files:
            if entry["original_path"] == original_path:
                return  # Already tracked

        entry: dict[str, Any] = {
            "original_path": original_path,
            "repo_path": repo_path,
            "added_at": datetime.now(UTC).isoformat(),
        }
        if is_template:
            entry["is_template"] = True
        self._data["files"].append(entry)
        self.save()

    def update_file(self, original_path: str, **kwargs: Any) -> bool:
        """Update metadata for a tracked file.

        Args:
            original_path: Path of the file to update.
            **kwargs: Fields to update (e.g., is_template=True).

        Returns:
            True if the file was found and updated.
        """
        for entry in self.files:
            if entry["original_path"] == original_path:
                entry.update(kwargs)
                self.save()
                return True
        return False

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

    def get_entry(self, original_path: str) -> dict[str, Any] | None:
        """Get a manifest entry by original path."""
        for entry in self.files:
            if entry["original_path"] == original_path:
                return entry
        return None

    def is_tracked(self, original_path: str) -> bool:
        return self.get_entry(original_path) is not None

    def get_template_files(self) -> list[dict[str, Any]]:
        """Get all files marked as templates."""
        return [e for e in self.files if e.get("is_template")]

    def get_concrete_files(self) -> list[dict[str, Any]]:
        """Get all files not marked as templates."""
        return [e for e in self.files if not e.get("is_template")]


class DotfileSync:
    """Main class for dotfile-sync operations."""

    def __init__(self, repo_dir: Path | None = None) -> None:
        self.repo_dir = repo_dir or _get_repo_dir()
        self.manifest_path = self.repo_dir / MANIFEST_FILE
        self.files_dir = self.repo_dir / FILES_DIR
        self.templates_dir = self.repo_dir / TEMPLATES_DIR
        self.contexts_dir = self.repo_dir / CONTEXTS_DIR

    def _ensure_initialized(self) -> None:
        """Raise NotInitializedError if the repo hasn't been initialized."""
        if not self.repo_dir.exists() or not (self.repo_dir / ".git").exists():
            raise NotInitializedError(
                "dotfile-sync is not initialized. Run `dotfile-sync init` first."
            )

    def _get_repo(self) -> Repo:
        """Get the GitPython Repo object."""
        return Repo(str(self.repo_dir))

    def _get_template_engine(self) -> TemplateEngine:
        """Get the template engine for this repo."""
        return create_template_engine(self.repo_dir)

    def _get_context_manager(self) -> ContextManager:
        """Get the context manager for this repo."""
        return create_context_manager(self.repo_dir)

    def _build_render_context(self) -> dict[str, Any]:
        """Build the template rendering context from manifest and contexts."""
        manifest = Manifest(self.manifest_path)
        ctx_mgr = self._get_context_manager()
        return ctx_mgr.build_context(
            machine_name=manifest.machine_name,
            profile=manifest.active_profile,
        )

    def init(self, remote_url: str | None = None) -> str:
        """Initialize the dotfile-sync repository."""
        if self.repo_dir.exists():
            return f"Repository already exists at {self.repo_dir}"

        # Create directory structure
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.contexts_dir.mkdir(parents=True, exist_ok=True)

        # Initialize manifest
        manifest = Manifest(self.manifest_path)
        manifest.save()

        # Create default context
        ctx_mgr = ContextManager(self.contexts_dir)
        ctx_mgr.set_context("default", {"hostname": _get_hostname()})

        # Initialize git repo
        repo = Repo.init(str(self.repo_dir))

        # Optionally add remote
        if remote_url:
            repo.create_remote("origin", remote_url)

        # Initial commit
        repo.index.add([MANIFEST_FILE])
        repo.index.add([str(self.contexts_dir)])
        repo.index.commit("chore: initialize dotfile-sync repository")

        return f"Initialized dotfile-sync repository at {self.repo_dir}"

    def track(self, path: str, *, as_template: bool = False) -> str:
        """Add a file or directory to the tracking manifest.

        Args:
            path: Path to the file or directory.
            as_template: If True, track as a template for variable substitution.
        """
        self._ensure_initialized()
        source = Path(path).expanduser().resolve()

        if not source.exists():
            raise DotfileSyncError(f"Path does not exist: {source}")

        manifest = Manifest(self.manifest_path)
        engine = self._get_template_engine()

        if source.is_dir():
            added = 0
            templates_detected = 0
            for file_path in sorted(source.rglob("*")):
                if file_path.is_file():
                    rel = file_path.relative_to(Path.home())
                    repo_path = str(rel).replace(os.sep, "/")
                    repo_path = _encode_repo_path(repo_path)
                    # Auto-detect template files
                    should_template = as_template or engine.is_template_file(file_path)
                    manifest.add_file(
                        str(file_path),
                        repo_path,
                        is_template=should_template,
                    )
                    added += 1
                    if should_template:
                        templates_detected += 1
            msg = f"Tracking {added} file(s) from {source}"
            if templates_detected:
                msg += f" ({templates_detected} as templates)"
            return msg
        else:
            rel = source.relative_to(Path.home())
            repo_path = str(rel).replace(os.sep, "/")
            repo_path = _encode_repo_path(repo_path)
            should_template = as_template or engine.is_template_file(source)
            if manifest.is_tracked(str(source)):
                return f"Already tracking: {source}"
            manifest.add_file(str(source), repo_path, is_template=should_template)
            label = " (template)" if should_template else ""
            return f"Now tracking: {source}{label}"

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
        """Copy all tracked files into the repo and commit.

        For template files, stores the raw template (with Jinja2 syntax) in
        the templates/ directory and a rendered snapshot in files/ for diffing.
        """
        self._ensure_initialized()
        manifest = Manifest(self.manifest_path)
        repo = self._get_repo()

        if not manifest.files:
            return "No files tracked. Use `dotfile-sync track <path>` to add files."

        backed_up = 0
        templates_backed = 0
        for entry in manifest.files:
            original = Path(entry["original_path"])
            repo_path = self.files_dir / entry["repo_path"]

            if not original.exists():
                continue

            repo_path.parent.mkdir(parents=True, exist_ok=True)

            if entry.get("is_template"):
                # Store the raw template in templates/ dir
                template_repo_path = self.templates_dir / entry["repo_path"]
                template_repo_path.parent.mkdir(parents=True, exist_ok=True)
                content: str | None = None
                try:
                    content = original.read_text(encoding="utf-8")
                    template_repo_path.write_text(content, encoding="utf-8")
                except UnicodeDecodeError:
                    shutil.copy2(original, template_repo_path)

                # Also store rendered snapshot in files/ for diffing
                if content is not None:
                    try:
                        context = self._build_render_context()
                        engine = self._get_template_engine()
                        rendered = engine.render(content, context)
                        repo_path.write_text(rendered, encoding="utf-8")
                    except TemplateRenderError:
                        shutil.copy2(original, repo_path)
                else:
                    shutil.copy2(original, repo_path)
                templates_backed += 1
            else:
                shutil.copy2(original, repo_path)
            backed_up += 1

        if backed_up == 0:
            return "No tracked files found on disk. Nothing to back up."

        # Stage and commit
        repo.index.add([str(self.files_dir)])
        repo.index.add([str(self.templates_dir)])
        repo.index.add([str(self.manifest_path)])

        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        commit_msg = message or f"backup: {backed_up} file(s) at {timestamp}"
        repo.index.commit(commit_msg)

        msg = f"Backed up {backed_up} file(s). Committed as: {commit_msg}"
        if templates_backed:
            msg += f" ({templates_backed} templates)"
        return msg

    def restore(self, only: str | None = None, *, render: bool = True) -> str:
        """Copy files from the repo back to their original locations.

        Args:
            only: If set, only restore this specific file path.
            render: If True, render templates with current context before
                    writing to disk. If False, write raw content.
        """
        self._ensure_initialized()
        manifest = Manifest(self.manifest_path)

        if not manifest.files:
            return "No files in manifest. Nothing to restore."

        restored = 0
        skipped = 0
        rendered = 0
        errors = 0
        for entry in manifest.files:
            if only and entry["original_path"] != only:
                continue

            original = Path(entry["original_path"])
            repo_path = self.files_dir / entry["repo_path"]

            if entry.get("is_template") and render:
                # For templates, render from the template source
                template_repo_path = self.templates_dir / entry["repo_path"]
                if not template_repo_path.exists():
                    skipped += 1
                    continue
                try:
                    context = self._build_render_context()
                    engine = self._get_template_engine()
                    template_content = template_repo_path.read_text(encoding="utf-8")
                    output = engine.render(template_content, context)
                    original.parent.mkdir(parents=True, exist_ok=True)
                    original.write_text(output, encoding="utf-8")
                    restored += 1
                    rendered += 1
                except TemplateRenderError:
                    errors += 1
                    continue
                except UnicodeDecodeError:
                    # Binary template - just copy
                    shutil.copy2(template_repo_path, original)
                    restored += 1
            else:
                if not repo_path.exists():
                    skipped += 1
                    continue

                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(repo_path, original)
                restored += 1

        msg = f"Restored {restored} file(s)"
        if rendered:
            msg += f" ({rendered} rendered from templates)"
        if skipped:
            msg += f", skipped {skipped} (not found in repo)"
        if errors:
            msg += f", {errors} template error(s)"
        return msg

    def diff(self) -> str:
        """Show differences between live files and the last backup.

        For template files, also shows the computed diff against the rendered
        version with the current context.
        """
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
                label = " [template]" if entry.get("is_template") else ""
                results.append(f"  {entry['original_path']}{label}: NEW (not yet backed up)")
                continue

            if not original.exists() and repo_path.exists():
                results.append(f"  {entry['original_path']}: DELETED on disk")
                continue

            # For templates, compare against rendered version
            if entry.get("is_template"):
                try:
                    context = self._build_render_context()
                    engine = self._get_template_engine()
                    template_path = self.templates_dir / entry["repo_path"]
                    if template_path.exists():
                        template_content = template_path.read_text(encoding="utf-8")
                        rendered = engine.render(template_content, context)
                        orig_content = original.read_text(encoding="utf-8")
                        if orig_content != rendered:
                            results.append(f"  {entry['original_path']} [template]: MODIFIED")
                        else:
                            results.append(f"  {entry['original_path']} [template]: up to date")
                        continue
                except (TemplateRenderError, UnicodeDecodeError):
                    pass

            # Fall back to binary comparison for non-template or failed templates
            orig_content = original.read_bytes()
            repo_content = repo_path.read_bytes()
            if orig_content != repo_content:
                results.append(f"  {entry['original_path']}: MODIFIED")
            else:
                results.append(f"  {entry['original_path']}: up to date")

        if not results:
            return "All tracked files are up to date."

        return "Status of tracked files:\n" + "\n".join(results)

    def diff_detailed(self, path: str | None = None) -> str:
        """Show detailed diff output (unified diff) for tracked files.

        Args:
            path: Optional specific file to diff. If None, diff all modified files.
        """
        self._ensure_initialized()
        manifest = Manifest(self.manifest_path)

        if not manifest.files:
            return "No files tracked. Nothing to diff."

        results = []
        for entry in manifest.files:
            if path and entry["original_path"] != path:
                continue

            original = Path(entry["original_path"])
            repo_path = self.files_dir / entry["repo_path"]

            if not original.exists() or not repo_path.exists():
                continue

            try:
                orig_lines = original.read_text(encoding="utf-8").splitlines(keepends=True)
                repo_lines = repo_path.read_text(encoding="utf-8").splitlines(keepends=True)
            except UnicodeDecodeError:
                continue

            if orig_lines != repo_lines:
                diff_lines = difflib.unified_diff(
                    repo_lines,
                    orig_lines,
                    fromfile=f"backup:{entry['repo_path']}",
                    tofile=f"live:{entry['original_path']}",
                )
                diff_text = "".join(diff_lines)
                if diff_text:
                    results.append(diff_text)

        return "\n".join(results) if results else "No differences found."

    def status(self) -> str:
        """Show which tracked files have been modified since last backup."""
        return self.diff()

    def list_tracked(self) -> str:
        """List all tracked files with template status."""
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
            tmpl_label = " [T]" if entry.get("is_template") else ""
            lines.append(f"  [{exists_on_disk}] [{backed_up}]{tmpl_label} {entry['original_path']}")

        lines.append("")
        lines.append("  [on disk] [backed up]  path")
        lines.append("  [T] = template file")
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


def _get_hostname() -> str:
    """Get the current machine's hostname."""
    import socket

    return socket.gethostname()


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
