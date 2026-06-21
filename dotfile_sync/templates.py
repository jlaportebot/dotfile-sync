"""Template engine for dotfile-sync using Jinja2."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader, TemplateError, Undefined, meta
from jinja2.sandbox import SandboxedEnvironment

from .errors import TemplateRenderError

# Template file extension
TEMPLATE_EXT = ".tmpl"


class StrictUndefined(Undefined):
    """Jinja2 undefined that raises on any access."""

    def __str__(self) -> str:
        raise TemplateRenderError(f"Undefined variable: {self._undefined_name}")

    def __iter__(self) -> Any:
        raise TemplateRenderError(f"Undefined variable: {self._undefined_name}")

    def __bool__(self) -> bool:
        raise TemplateRenderError(f"Undefined variable: {self._undefined_name}")


class TemplateEngine:
    """Manages Jinja2 template rendering for dotfiles."""

    def __init__(self, template_dir: Path | None = None) -> None:
        """Initialize the template engine.

        Args:
            template_dir: Optional directory to load templates from.
        """
        self.template_dir = template_dir
        # Use SandboxedEnvironment for security
        self.env = SandboxedEnvironment(
            loader=FileSystemLoader(str(template_dir)) if template_dir else None,
            autoescape=False,
            undefined=StrictUndefined,
        )

    def render(self, template_content: str, context: dict[str, Any]) -> str:
        """Render a template string with the given context.

        Args:
            template_content: The template content as a string.
            context: Dictionary of variables for template rendering.

        Returns:
            Rendered template as string.

        Raises:
            TemplateRenderError: If rendering fails.
        """
        try:
            template = self.env.from_string(template_content)
            return template.render(**context)
        except TemplateError as e:
            raise TemplateRenderError(f"Failed to render template: {e}") from e

    def render_file(self, template_path: Path, context: dict[str, Any]) -> str:
        """Render a template file with the given context.

        Args:
            template_path: Path to the template file.
            context: Dictionary of variables for template rendering.

        Returns:
            Rendered template as string.

        Raises:
            TemplateRenderError: If rendering fails.
        """
        try:
            if self.template_dir:
                rel_path = template_path.relative_to(self.template_dir)
                template = self.env.get_template(str(rel_path))
            else:
                self.env.loader = FileSystemLoader(str(template_path.parent))
                template = self.env.get_template(template_path.name)
            return template.render(**context)
        except TemplateError as e:
            raise TemplateRenderError(f"Failed to render template {template_path}: {e}") from e

    def extract_variables(self, template_content: str) -> set[str]:
        """Extract all variable names used in a template.

        Args:
            template_content: The template content as a string.

        Returns:
            Set of variable names used in the template.
        """
        ast = self.env.parse(template_content)
        return meta.find_undeclared_variables(ast)

    def is_template(self, content: str) -> bool:
        """Check if content contains template syntax.

        Args:
            content: File content to check.

        Returns:
            True if content appears to be a template.
        """
        return "{{" in content or "{%" in content or "{#" in content

    def is_template_file(self, path: Path) -> bool:
        """Check if a file is a template based on extension or content.

        Args:
            path: Path to check.

        Returns:
            True if file is a template.
        """
        if path.suffix == TEMPLATE_EXT:
            return True
        try:
            content = path.read_text(encoding="utf-8")
            return self.is_template(content)
        except Exception:
            return False


class ContextManager:
    """Manages template contexts for different machines/profiles."""

    def __init__(self, context_dir: Path) -> None:
        """Initialize the context manager.

        Args:
            context_dir: Directory to store context files.
        """
        self.context_dir = context_dir
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self._contexts: dict[str, dict[str, Any]] = {}
        self._load_contexts()

    def _load_contexts(self) -> None:
        """Load all context files from the context directory."""
        import yaml

        for context_file in self.context_dir.glob("*.yaml"):
            name = context_file.stem
            try:
                self._contexts[name] = yaml.safe_load(context_file.read_text()) or {}
            except Exception:
                self._contexts[name] = {}

    def get_context(self, name: str) -> dict[str, Any]:
        """Get a context by name.

        Args:
            name: Context name (e.g., 'machine', 'work', 'personal').

        Returns:
            Context dictionary.
        """
        return self._contexts.get(name, {}).copy()

    def set_context(self, name: str, context: dict[str, Any]) -> None:
        """Set a context.

        Args:
            name: Context name.
            context: Context dictionary.
        """
        self._contexts[name] = context
        self._save_context(name)

    def _save_context(self, name: str) -> None:
        """Save a context to disk.

        Args:
            name: Context name.
        """
        import yaml

        context_file = self.context_dir / f"{name}.yaml"
        context_file.write_text(yaml.dump(self._contexts[name], default_flow_style=False))

    def list_contexts(self) -> list[str]:
        """List all available context names."""
        return list(self._contexts.keys())

    def merge_contexts(self, *names: str) -> dict[str, Any]:
        """Merge multiple contexts, later ones override earlier.

        Args:
            *names: Context names to merge in order.

        Returns:
            Merged context dictionary.
        """
        merged: dict[str, Any] = {}
        for name in names:
            merged.update(self.get_context(name))
        return merged

    def build_context(
        self,
        machine_name: str | None = None,
        profile: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a complete context for rendering.

        Merges in order: default -> machine -> profile -> environment -> extra

        Args:
            machine_name: Name of the machine context.
            profile: Name of the profile context.
            extra: Additional variables to include.

        Returns:
            Complete merged context.
        """
        context: dict[str, Any] = {}

        # Default context
        context.update(self.get_context("default"))

        # Machine-specific context
        if machine_name:
            context.update(self.get_context(f"machine-{machine_name}"))

        # Profile context (work, personal, server, etc.)
        if profile:
            context.update(self.get_context(f"profile-{profile}"))

        # Environment variables (prefixed with DOTFILE_SYNC_)
        for key, value in os.environ.items():
            if key.startswith("DOTFILE_SYNC_"):
                context[key[len("DOTFILE_SYNC_") :].lower()] = value

        # Extra variables (highest priority)
        if extra:
            context.update(extra)

        return context


def create_template_engine(repo_dir: Path) -> TemplateEngine:
    """Create a template engine for the given repo.

    Args:
        repo_dir: The dotfile-sync repository directory.

    Returns:
        Configured TemplateEngine instance.
    """
    template_dir = repo_dir / "templates"
    return TemplateEngine(template_dir=template_dir if template_dir.exists() else None)


def create_context_manager(repo_dir: Path) -> ContextManager:
    """Create a context manager for the given repo.

    Args:
        repo_dir: The dotfile-sync repository directory.

    Returns:
        Configured ContextManager instance.
    """
    context_dir = repo_dir / "contexts"
    return ContextManager(context_dir)
