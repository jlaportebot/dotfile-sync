"""Custom exceptions for dotfile-sync."""

from __future__ import annotations


class DotfileSyncError(Exception):
    """Base exception for dotfile-sync errors."""


class NotInitializedError(DotfileSyncError):
    """Raised when the dotfile-sync repo has not been initialized."""


class TemplateContextError(DotfileSyncError):
    """Raised when there's an error with template context."""


class TemplateRenderError(DotfileSyncError):
    """Raised when template rendering fails."""
