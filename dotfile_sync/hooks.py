"""Hook system for dotfile-sync lifecycle events.

Provides pre/post hooks for backup and restore operations, allowing
users to run custom commands before or after syncing dotfiles.
"""

from __future__ import annotations

import json
import logging
import subprocess
from enum import StrEnum
from pathlib import Path

from .errors import DotfileSyncError

logger = logging.getLogger(__name__)


class HookEvent(StrEnum):
    """Lifecycle events that support hooks."""

    PRE_BACKUP = "pre_backup"
    POST_BACKUP = "post_backup"
    PRE_RESTORE = "pre_restore"
    POST_RESTORE = "post_restore"
    PRE_TRACK = "pre_track"
    POST_TRACK = "post_track"
    PRE_PUSH = "pre_push"
    POST_PUSH = "post_push"


class HookResult:
    """Result of a hook execution."""

    def __init__(
        self,
        event: HookEvent,
        command: str,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> None:
        self.event = event
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def __repr__(self) -> str:
        status = "ok" if self.success else f"exit({self.exit_code})"
        return f"HookResult({self.event.value}: {self.command!r} -> {status})"


class HookConfig:
    """Manages hook configuration stored in hooks.json."""

    def __init__(self, hooks_path: Path) -> None:
        self.hooks_path = hooks_path
        self._hooks: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        """Load hooks configuration from disk."""
        if not self.hooks_path.exists():
            self._hooks = {}
            return
        try:
            data = json.loads(self.hooks_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._hooks = data
        except (json.JSONDecodeError, OSError):
            self._hooks = {}

    def save(self) -> None:
        """Persist hook configuration to disk."""
        self.hooks_path.parent.mkdir(parents=True, exist_ok=True)
        self.hooks_path.write_text(
            json.dumps(self._hooks, indent=2) + "\n",
            encoding="utf-8",
        )

    def get_hooks(self, event: HookEvent) -> list[str]:
        """Get hook commands for an event."""
        return list(self._hooks.get(event.value, []))

    def add_hook(self, event: HookEvent, command: str) -> None:
        """Add a hook command for an event."""
        if event.value not in self._hooks:
            self._hooks[event.value] = []
        self._hooks[event.value].append(command)
        self.save()

    def remove_hook(self, event: HookEvent, index: int) -> bool:
        """Remove a hook by index. Returns True if found."""
        hooks = self._hooks.get(event.value, [])
        if 0 <= index < len(hooks):
            hooks.pop(index)
            if not hooks:
                del self._hooks[event.value]
            else:
                self._hooks[event.value] = hooks
            self.save()
            return True
        return False

    def clear_hooks(self, event: HookEvent | None = None) -> None:
        """Clear hooks for an event, or all hooks if event is None."""
        if event is None:
            self._hooks.clear()
        elif event.value in self._hooks:
            del self._hooks[event.value]
        self.save()

    def list_all(self) -> dict[str, list[str]]:
        """Get all hooks organized by event."""
        return dict(self._hooks)


class HookRunner:
    """Executes hook commands for lifecycle events."""

    def __init__(
        self, config: HookConfig, working_dir: Path | None = None, hook_timeout: int = 300
    ) -> None:
        self.config = config
        self.working_dir = working_dir
        self.hook_timeout = hook_timeout

    def run_hooks(
        self,
        event: HookEvent,
        env: dict[str, str] | None = None,
        *,
        abort_on_failure: bool = True,
    ) -> list[HookResult]:
        """Run all hooks for an event.

        Args:
            event: The lifecycle event.
            env: Additional environment variables for hooks.
            abort_on_failure: If True, stop after first failure.

        Returns:
            List of hook results.

        Raises:
            DotfileSyncError: If a hook fails and abort_on_failure is True.
        """
        commands = self.config.get_hooks(event)
        results: list[HookResult] = []

        hook_env: dict[str, str] = {}
        if env:
            hook_env.update(env)
        # Add event name to environment
        hook_env["DOTFILE_SYNC_HOOK_EVENT"] = event.value

        for command in commands:
            result = self._execute(command, hook_env)
            results.append(result)

            if not result.success:
                logger.warning(
                    "Hook %s failed: %s (exit %d)",
                    event.value,
                    command,
                    result.exit_code,
                )
                if abort_on_failure:
                    raise DotfileSyncError(
                        f"Hook for {event.value} failed: {command} "
                        f"(exit code {result.exit_code}): {result.stderr}"
                    )

        return results

    def _execute(
        self,
        command: str,
        env: dict[str, str] | None = None,
    ) -> HookResult:
        """Execute a single hook command.

        Args:
            command: Shell command to execute.
            env: Optional environment variables.

        Returns:
            HookResult with execution details.
        """
        import os

        full_env = dict(os.environ)
        if env:
            full_env.update(env)

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.working_dir) if self.working_dir else None,
                env=full_env,
                timeout=self.hook_timeout,
            )
            return HookResult(
                event=HookEvent("pre_backup"),  # placeholder, set by caller
                command=command,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except subprocess.TimeoutExpired:
            return HookResult(
                event=HookEvent("pre_backup"),
                command=command,
                exit_code=124,
                stdout="",
                stderr=f"Hook timed out after {self.hook_timeout} seconds",
            )
        except Exception as exc:
            return HookResult(
                event=HookEvent("pre_backup"),
                command=command,
                exit_code=1,
                stdout="",
                stderr=str(exc),
            )


def create_hook_config(repo_dir: Path) -> HookConfig:
    """Create a HookConfig for the given repo directory.

    Args:
        repo_dir: The dotfile-sync repository directory.

    Returns:
        Configured HookConfig.
    """
    return HookConfig(repo_dir / "hooks.json")


def create_hook_runner(repo_dir: Path, hook_timeout: int = 300) -> HookRunner:
    """Create a HookRunner for the given repo directory.

    Args:
        repo_dir: The dotfile-sync repository directory.
        hook_timeout: Timeout in seconds for hook execution (default 300).

    Returns:
        Configured HookRunner.
    """
    config = create_hook_config(repo_dir)
    return HookRunner(config, working_dir=repo_dir, hook_timeout=hook_timeout)


# Environment variable names passed to hooks
ENV_FILE_PATH = "DOTFILE_SYNC_FILE_PATH"
ENV_OPERATION = "DOTFILE_SYNC_OPERATION"
ENV_REPO_DIR = "DOTFILE_SYNC_REPO_DIR"
