# src/middleware/skills_sync.py
"""
技能同步中间件

在每个 Agent 运行周期开始前，将本地 src/skills/ 下的技能文件与沙箱同步。
检测到变化时，向对话中插入系统通知，提醒 Agent 有新技能可用。
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage

from deepagents.backends.sandbox import BaseSandbox  # 使用通用的沙箱后端协议

from agent.core.config import LOCAL_SKILLS_DIR, SANDBOX_SKILLS_ROOT


class SkillsSyncMiddleware(AgentMiddleware):
    """技能文件同步中间件，依赖沙箱后端的文件操作能力。"""

    def __init__(self, backend: BaseSandbox) -> None:
        super().__init__()
        self.backend = backend
        # 缓存本地文件哈希，避免重复同步
        self._last_hashes: Dict[str, str] = {}

    # --------------------- 钩子 ---------------------
    def before_agent(self, state: Dict[str, Any], runtime: Any) -> Optional[Dict[str, Any]]:
        new_skills = self._sync_files()
        if new_skills:
            return self._make_notification(new_skills)
        return None

    async def abefore_agent(self, state: Dict[str, Any], runtime: Any) -> Optional[Dict[str, Any]]:
        import asyncio
        loop = asyncio.get_running_loop()
        new_skills = await loop.run_in_executor(None, self._sync_files)
        if new_skills:
            return self._make_notification(new_skills)
        return None

    # --------------------- 文件同步 ---------------------
    def _sync_files(self) -> List[str]:
        """扫描本地技能目录，将新增/修改的文件上传到沙箱。

        Returns:
            发生变化的技能名称列表。
        """
        local_skills_dir = Path(LOCAL_SKILLS_DIR)
        if not local_skills_dir.exists():
            return []

        updated_skills: List[str] = []

        for skill_dir in local_skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_name = skill_dir.name
            sandbox_skill_dir = f"{SANDBOX_SKILLS_ROOT}/{skill_name}"

            files_to_upload: List[Tuple[str, bytes]] = []
            has_changes = False

            for local_file in skill_dir.rglob("*"):
                if not local_file.is_file():
                    continue
                relative_path = local_file.relative_to(skill_dir).as_posix()
                sandbox_path = f"{sandbox_skill_dir}/{relative_path}"

                with open(local_file, "rb") as f:
                    local_content = f.read()
                local_hash = hashlib.md5(local_content).hexdigest()
                cache_key = f"{skill_name}/{relative_path}"

                # 本地哈希未变，跳过
                if self._last_hashes.get(cache_key) == local_hash:
                    continue

                # 对比沙箱文件（先 test -f 避免 download_files 对 404 打 ERROR）
                check = self.backend.execute(f"test -f {sandbox_path}")
                if check.exit_code == 0:
                    try:
                        results = self.backend.download_files([sandbox_path])
                        if results and results[0].content and not results[0].error:
                            remote_content = results[0].content
                            if isinstance(remote_content, str):
                                remote_content = remote_content.encode("utf-8")
                            remote_hash = hashlib.md5(remote_content).hexdigest()
                            if remote_hash == local_hash:
                                self._last_hashes[cache_key] = local_hash
                                continue
                    except Exception:
                        pass  # 读取失败，需要上传

                files_to_upload.append((sandbox_path, local_content))
                self._last_hashes[cache_key] = local_hash
                has_changes = True

            if has_changes:
                self.backend.upload_files(files_to_upload)
                updated_skills.append(skill_name)

        return updated_skills

    # --------------------- 通知生成 ---------------------
    def _make_notification(self, skill_names: List[str]) -> Dict[str, Any]:
        skills_list = "\n".join(f"- {name}" for name in skill_names)
        notice = (
            f"[系统通知] 以下技能包已更新：\n{skills_list}\n"
            "请使用 `ls /skills/` 查看详情，对当前任务可能有帮助。"
        )
        return {"messages": [SystemMessage(content=notice)]}
