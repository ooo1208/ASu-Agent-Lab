"""Regression tests for local Agent resource paths after package reorganization."""

from pathlib import Path

from agent.core.config import (
    AGENT_DIR,
    DOWNLOAD_DIR,
    LOCAL_AGENTS_MD,
    LOCAL_SKILLS_DIR,
    LOCAL_SUBAGENT_CONFIG_DIR,
    SRC_DIR,
)


def test_agent_resource_paths_resolve_from_source_root() -> None:
    expected_src_dir = (Path(__file__).resolve().parents[1] / "src").resolve()

    assert SRC_DIR == expected_src_dir
    assert AGENT_DIR == expected_src_dir / "agent"
    assert LOCAL_SKILLS_DIR == expected_src_dir / "skills"
    assert DOWNLOAD_DIR == expected_src_dir / "download"
    assert LOCAL_SUBAGENT_CONFIG_DIR == expected_src_dir / "agent" / "subagents"
    assert LOCAL_AGENTS_MD == expected_src_dir / "agent" / "memory" / "AGENTS.md"


def test_required_agent_resources_exist() -> None:
    assert LOCAL_AGENTS_MD.is_file()
    assert LOCAL_SKILLS_DIR.is_dir()
    assert LOCAL_SUBAGENT_CONFIG_DIR.is_dir()
