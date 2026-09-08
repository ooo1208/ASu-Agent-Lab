"""Regression tests for the prebuilt sandbox Python environment check."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.backends import sandbox_setup


class FakeBackend:
    """Record sandbox commands and return configured command results."""

    def __init__(self, exit_code: int, output: str = "") -> None:
        self.exit_code = exit_code
        self.output = output
        self.commands: list[tuple[str, int | None]] = []

    def execute(self, command: str, *, timeout: int | None = None):
        """Return the configured response for every command."""
        self.commands.append((command, timeout))
        return SimpleNamespace(exit_code=self.exit_code, output=self.output)


def test_prebuilt_environment_uses_one_fast_check():
    """A valid image must not invoke pip or runtime installation."""
    backend = FakeBackend(exit_code=0)

    sandbox_setup._ensure_python_environment(
        backend,
        require_image_marker=True,
    )

    assert len(backend.commands) == 1
    command, timeout = backend.commands[0]
    assert sandbox_setup._IMAGE_MARKER in command
    assert "import bs4" in command
    assert "pip install" not in command
    assert timeout == 30


def test_broken_prebuilt_environment_fails_fast(monkeypatch):
    """Production defaults must reject a broken image without online installs."""
    monkeypatch.setattr(sandbox_setup, "RUNTIME_INSTALL_FALLBACK", False)
    backend = FakeBackend(exit_code=1, output="missing dependency")

    with pytest.raises(RuntimeError, match="预构建 Python 环境不完整"):
        sandbox_setup._ensure_python_environment(
            backend,
            require_image_marker=True,
        )

    assert len(backend.commands) == 1
    assert all("pip install" not in command for command, _ in backend.commands)

