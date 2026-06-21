"""Tests for dotfile-sync template engine."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dotfile_sync.errors import DotfileSyncError, TemplateContextError, TemplateRenderError
from dotfile_sync.templates import (
    ContextManager,
    TemplateEngine,
)


class TestTemplateEngine:
    """Tests for the TemplateEngine class."""

    def test_render_simple_variable(self) -> None:
        engine = TemplateEngine()
        result = engine.render("Hello {{ name }}!", {"name": "World"})
        assert result == "Hello World!"

    def test_render_multiple_variables(self) -> None:
        engine = TemplateEngine()
        template = "[user]\n name = {{ name }}\n email = {{ email }}"
        result = engine.render(template, {"name": "John", "email": "john@dev.io"})
        assert "John" in result
        assert "john@dev.io" in result

    def test_render_conditional(self) -> None:
        engine = TemplateEngine()
        template = "{% if dev_mode %}debug=true{% else %}debug=false{% endif %}"
        assert engine.render(template, {"dev_mode": True}) == "debug=true"
        assert engine.render(template, {"dev_mode": False}) == "debug=false"

    def test_render_loop(self) -> None:
        engine = TemplateEngine()
        template = "{% for item in items %}{{ item }}\n{% endfor %}"
        result = engine.render(template, {"items": ["a", "b", "c"]})
        assert "a" in result
        assert "b" in result
        assert "c" in result

    def test_render_missing_variable_raises(self) -> None:
        engine = TemplateEngine()
        with pytest.raises(TemplateRenderError, match="Undefined variable"):
            engine.render("{{ missing }}", {})

    def test_render_invalid_syntax_raises(self) -> None:
        engine = TemplateEngine()
        with pytest.raises(TemplateRenderError, match="Failed to render"):
            engine.render("{% if %}", {})

    def test_extract_variables(self) -> None:
        engine = TemplateEngine()
        template = "{{ name }} - {{ email }} {% if active %}yes{% endif %}"
        variables = engine.extract_variables(template)
        assert "name" in variables
        assert "email" in variables
        assert "active" in variables

    def test_extract_variables_no_duplicates(self) -> None:
        engine = TemplateEngine()
        template = "{{ name }} and {{ name }}"
        variables = engine.extract_variables(template)
        assert len(variables) == 1

    def test_extract_variables_empty(self) -> None:
        engine = TemplateEngine()
        variables = engine.extract_variables("no templates here")
        assert len(variables) == 0

    def test_is_template_with_jinja_syntax(self) -> None:
        engine = TemplateEngine()
        assert engine.is_template("{{ variable }}") is True
        assert engine.is_template("{% if condition %}yes{% endif %}") is True
        assert engine.is_template("{# comment #}") is True
        assert engine.is_template("just text") is False

    def test_is_template_file_by_extension(self, tmp_path: Path) -> None:
        engine = TemplateEngine()
        tmpl_file = tmp_path / "config.tmpl"
        tmpl_file.write_text("content")
        assert engine.is_template_file(tmpl_file) is True

    def test_is_template_file_by_content(self, tmp_path: Path) -> None:
        engine = TemplateEngine()
        regular_file = tmp_path / "config.conf"
        regular_file.write_text("{{ variable }}")
        assert engine.is_template_file(regular_file) is True

    def test_is_template_file_plain(self, tmp_path: Path) -> None:
        engine = TemplateEngine()
        plain_file = tmp_path / "plain.txt"
        plain_file.write_text("no templates here")
        assert engine.is_template_file(plain_file) is False

    def test_render_gitconfig_template(self) -> None:
        engine = TemplateEngine()
        template = """[user]
 name = {{ git_name }}
 email = {{ git_email }}
[core]
 editor = {{ editor }}
"""
        result = engine.render(
            template,
            {
                "git_name": "John Doe",
                "git_email": "john@example.com",
                "editor": "vim",
            },
        )
        assert "John Doe" in result
        assert "john@example.com" in result
        assert "vim" in result

    def test_render_bashrc_template(self) -> None:
        engine = TemplateEngine()
        template = """#!/bin/bash
export PATH=$PATH:{{ custom_path }}
export PS1="\\u@{{ hostname }}\\w$ "
{% if dev_mode -%}
export DEBUG=1
{%- endif %}"""
        result = engine.render(
            template,
            {
                "custom_path": "/opt/bin",
                "hostname": "myserver",
                "dev_mode": True,
            },
        )
        assert "/opt/bin" in result
        assert "myserver" in result
        assert "DEBUG=1" in result


class TestContextManager:
    """Tests for the ContextManager class."""

    def test_create_and_get_context(self, tmp_path: Path) -> None:
        ctx_mgr = ContextManager(tmp_path / "contexts")
        ctx_mgr.set_context("default", {"hostname": "myserver"})
        ctx_obj = ctx_mgr.get_context("default")
        assert ctx_obj["hostname"] == "myserver"

    def test_get_nonexistent_context(self, tmp_path: Path) -> None:
        ctx_mgr = ContextManager(tmp_path / "contexts")
        ctx_obj = ctx_mgr.get_context("nonexistent")
        assert ctx_obj == {}

    def test_list_contexts(self, tmp_path: Path) -> None:
        ctx_mgr = ContextManager(tmp_path / "contexts")
        ctx_mgr.set_context("default", {"a": 1})
        ctx_mgr.set_context("machine-laptop", {"b": 2})
        names = ctx_mgr.list_contexts()
        assert "default" in names
        assert "machine-laptop" in names

    def test_merge_contexts(self, tmp_path: Path) -> None:
        ctx_mgr = ContextManager(tmp_path / "contexts")
        ctx_mgr.set_context("default", {"a": "1", "b": "2"})
        ctx_mgr.set_context("machine-laptop", {"b": "2-override", "c": "3"})
        merged = ctx_mgr.merge_contexts("default", "machine-laptop")
        assert merged["a"] == "1"
        assert merged["b"] == "2-override"
        assert merged["c"] == "3"

    def test_build_context_default(self, tmp_path: Path) -> None:
        ctx_mgr = ContextManager(tmp_path / "contexts")
        ctx_mgr.set_context("default", {"hostname": "myserver"})
        built = ctx_mgr.build_context()
        assert built["hostname"] == "myserver"

    def test_build_context_with_machine(self, tmp_path: Path) -> None:
        ctx_mgr = ContextManager(tmp_path / "contexts")
        ctx_mgr.set_context("default", {"hostname": "default-host"})
        ctx_mgr.set_context("machine-laptop", {"hostname": "laptop-host", "user": "john"})
        built = ctx_mgr.build_context(machine_name="laptop")
        assert built["hostname"] == "laptop-host"
        assert built["user"] == "john"

    def test_build_context_with_profile(self, tmp_path: Path) -> None:
        ctx_mgr = ContextManager(tmp_path / "contexts")
        ctx_mgr.set_context("default", {"hostname": "default-host"})
        ctx_mgr.set_context("profile-work", {"email": "john@work.com"})
        built = ctx_mgr.build_context(profile="work")
        assert built["hostname"] == "default-host"
        assert built["email"] == "john@work.com"

    def test_build_context_with_extra(self, tmp_path: Path) -> None:
        ctx_mgr = ContextManager(tmp_path / "contexts")
        ctx_mgr.set_context("default", {"hostname": "myserver"})
        built = ctx_mgr.build_context(extra={"custom": "value"})
        assert built["custom"] == "value"

    def test_context_persists_to_disk(self, tmp_path: Path) -> None:
        ctx_dir = tmp_path / "contexts"
        ctx_mgr = ContextManager(ctx_dir)
        ctx_mgr.set_context("default", {"hostname": "myserver"})

        # Create a new manager to test persistence
        ctx_mgr2 = ContextManager(ctx_dir)
        ctx_obj = ctx_mgr2.get_context("default")
        assert ctx_obj["hostname"] == "myserver"

    def test_context_yaml_format(self, tmp_path: Path) -> None:
        ctx_dir = tmp_path / "contexts"
        ctx_mgr = ContextManager(ctx_dir)
        ctx_mgr.set_context("default", {"hostname": "myserver", "port": 8080})

        # Check the file format
        ctx_file = ctx_dir / "default.yaml"
        assert ctx_file.exists()
        data = yaml.safe_load(ctx_file.read_text())
        assert data["hostname"] == "myserver"


class TestTemplateEngineWithFile:
    """Tests for rendering template files."""

    def test_render_file_with_loader(self, tmp_path: Path) -> None:
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        template_file = template_dir / "config.conf"
        template_file.write_text("Hello {{ name }}!")

        engine = TemplateEngine(template_dir=template_dir)
        result = engine.render_file(template_file, {"name": "World"})
        assert result == "Hello World!"

    def test_render_file_absolute_path(self, tmp_path: Path) -> None:
        template_file = tmp_path / "config.conf"
        template_file.write_text("user={{ user }}")

        engine = TemplateEngine()
        result = engine.render_file(template_file, {"user": "admin"})
        assert result == "user=admin"
