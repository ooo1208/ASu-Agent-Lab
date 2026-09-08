"""Regression tests for per-user persisted skill isolation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langgraph.store.memory import InMemoryStore

from agent.core.config import user_skills_namespace
from agent.middlewares.user_skills_restore import UserSkillsRestoreMiddleware
from agent.tools.assign_skill import _persist_skill


class FakeSandboxBackend:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def execute(self, command: str):
        if command.startswith("find "):
            source_dir = command.removeprefix("find ").removesuffix(" -type f")
            paths = sorted(
                path for path in self.files if path.startswith(source_dir + "/")
            )
            return SimpleNamespace(exit_code=0, output="\n".join(paths))
        return SimpleNamespace(exit_code=0, output="")

    def download_files(self, paths: list[str]):
        return [
            SimpleNamespace(
                content=self.files.get(path),
                error=None if path in self.files else "missing",
            )
            for path in paths
        ]


def test_user_skills_namespace_is_private_and_stable():
    assert user_skills_namespace("user-a") == ("users", "user-a", "skills")
    assert user_skills_namespace(" user-a ") == ("users", "user-a", "skills")
    assert user_skills_namespace("user-a") != user_skills_namespace("user-b")
    with pytest.raises(ValueError):
        user_skills_namespace("  ")


@pytest.mark.asyncio
async def test_same_named_skill_does_not_cross_users():
    store = InMemoryStore()
    skill_path = "/skills/main/shared-name/SKILL.md"

    await _persist_skill(
        FakeSandboxBackend({skill_path: b"user A version"}),
        store,
        user_skills_namespace("user-a"),
        "shared-name",
        "main",
    )
    await _persist_skill(
        FakeSandboxBackend({skill_path: b"user B version"}),
        store,
        user_skills_namespace("user-b"),
        "shared-name",
        "main",
    )

    restored_a = await UserSkillsRestoreMiddleware(
        FakeSandboxBackend({}), user_skills_namespace("user-a")
    )._collect_skills(store)
    restored_b = await UserSkillsRestoreMiddleware(
        FakeSandboxBackend({}), user_skills_namespace("user-b")
    )._collect_skills(store)

    assert restored_a == [(skill_path, b"user A version")]
    assert restored_b == [(skill_path, b"user B version")]


@pytest.mark.asyncio
async def test_restore_reads_more_than_default_store_page():
    store = InMemoryStore()
    namespace = user_skills_namespace("many-files-user")
    for index in range(23):
        await store.aput(
            namespace,
            f"/main/many-files/file-{index}.txt",
            {"content": [f"content-{index}"]},
        )

    restored = await UserSkillsRestoreMiddleware(
        FakeSandboxBackend({}), namespace
    )._collect_skills(store)

    assert len(restored) == 23
    assert {path for path, _ in restored} == {
        f"/skills/main/many-files/file-{index}.txt" for index in range(23)
    }
