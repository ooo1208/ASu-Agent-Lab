# src/backends/sandbox_setup.py
"""
OpenSandbox 沙箱的初始化与文件播种模块。

职责:
1. 获取或创建 OpenSandbox 沙箱，包装为 OpenSandboxBackend。
2. 播种技能文件（技能包 SKILL.md）。

注意：AGENTS.md 已迁移到 StoreBackend（全局共享），不经过沙箱。
用户长期记忆（/memories/）由 CompositeBackend 路由到 StoreBackend 持久化。
运行时的增量技能同步由 SkillsSyncMiddleware 负责。
"""
import os
from datetime import timedelta
from pathlib import Path
from typing import List, Tuple

from opensandbox import SandboxSync

from agent.backends.custom_opensandbox import OpenSandboxBackend
from agent.core.config import (
    LOCAL_SKILLS_DIR,
    SANDBOX_SKILLS_ROOT,
)

PROJECT_SANDBOX_IMAGE = "asu-agent-sandbox:v1"
DEFAULT_SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", PROJECT_SANDBOX_IMAGE)
RUNTIME_INSTALL_FALLBACK = os.environ.get(
    "SANDBOX_RUNTIME_INSTALL_FALLBACK", "false"
).lower() in {"1", "true", "yes"}


def setup_sandbox(config, sandbox_id=None, image=None) -> OpenSandboxBackend:
    """
    获取或创建沙箱，播种基础文件。

    Args:
        config: ConnectionConfigSync 配置。
        sandbox_id: 可选，要连接的现有沙箱 ID。
        image: 可选，创建新沙箱时使用的镜像。

    Returns:
        OpenSandboxBackend 实例。
    """
    created_new = False
    if sandbox_id:
        print(f"[INFO] 正在连接到现有沙箱: {sandbox_id}")
        try:
            sandbox = SandboxSync.connect(sandbox_id, connection_config=config)
            print(f"[INFO] 成功连接到沙箱: {sandbox_id}")
        except Exception as e:
            print(f"[WARNING] 连接沙箱失败: {e}，将创建新沙箱")
            sandbox_id = None

    if not sandbox_id:
        if not image:
            image = DEFAULT_SANDBOX_IMAGE

        print(f"[INFO] 正在创建新沙箱，使用镜像: {image}")
        sandbox = SandboxSync.create(
            image,
            entrypoint=["/opt/opensandbox/code-interpreter.sh"],
            env={"PYTHON_VERSION": "3.11"},
            resource={"cpu": "2", "memory": "4Gi"},
            timeout=timedelta(hours=2),
            connection_config=config,
            # network_policy=NetworkPolicy(  # 沙箱网络路由限制策略
            #     defaultAction="deny",
            #     egress=[
            #         NetworkRule(action="allow", target="pypi.org"),
            #         NetworkRule(action="allow", target="*.github.com"),
            #     ]
            # )
        )
        created_new = True

    backend = OpenSandboxBackend(sandbox=sandbox)
    print(f"[INFO] 沙箱就绪，ID: {sandbox.id}")

    # 预创建 skills 需要的目录，避免 Agent 运行时遇到 FileNotFoundError
    _ensure_dirs(backend)

    # 播种基础文件（AGENTS.md、Skills）
    _seed_files(backend)

    # 预构建镜像只做快速完整性检查；旧沙箱重连时允许没有镜像 marker，
    # 但仍必须具备完整依赖。
    _ensure_python_environment(
        backend,
        require_image_marker=created_new and image == PROJECT_SANDBOX_IMAGE,
    )

    return backend


# skills 运行时依赖的目录（需在沙箱中预创建）
_SKILL_DIRS = ["/analysis/temp", "/analysis/tasks", "/data"]

# 所有 Python 依赖统一安装到此 venv，避开系统 Python 的 externally managed 限制
_VENV_PATH = "/opt/skills-venv"
_VENV_PIP = f"{_VENV_PATH}/bin/pip"
# skills 运行时需要的 Python 第三方包
_PREINSTALL_PACKAGES = [
    "numpy",
    "pandas",
    "matplotlib",
    "requests",
    "beautifulsoup4",
    "lxml",
    "markdownify",
]

_IMAGE_MARKER = f"{_VENV_PATH}/.erp-openclaw-image-v1"
_IMPORT_CHECK = (
    "import bs4, lxml, markdownify, matplotlib, numpy, pandas, requests; "
    "print('sandbox-python-env-ok')"
)


def _ensure_dirs(backend: OpenSandboxBackend) -> None:
    """预创建 skills 运行所需的目录，避免 FileNotFoundError。"""
    for d in _SKILL_DIRS:
        backend.execute(f"mkdir -p {d}")


# 阿里云 PyPI 镜像，沙箱内走内网加速
_PYPI_INDEX = "https://mirrors.aliyun.com/pypi/simple/"
# pip install 通用参数
_PIP_INSTALL_ARGS = f"-i {_PYPI_INDEX} --default-timeout=60 --no-input -q"


def _ensure_python_environment(
    backend: OpenSandboxBackend,
    *,
    require_image_marker: bool = False,
) -> None:
    """快速验证预构建环境，必要时按显式开发开关执行现场安装。"""
    marker_check = f"test -f {_IMAGE_MARKER} && " if require_image_marker else ""
    result = backend.execute(
        f'{marker_check}{_VENV_PATH}/bin/python -c "{_IMPORT_CHECK}"',
        timeout=30,
    )
    if result.exit_code == 0:
        print("[INFO] 沙箱 Python 依赖快速检查通过")
        return

    if not RUNTIME_INSTALL_FALLBACK:
        raise RuntimeError(
            "沙箱预构建 Python 环境不完整。请重新构建 asu-agent-sandbox:v1；"
            "开发环境可临时设置 SANDBOX_RUNTIME_INSTALL_FALLBACK=true。"
            f" 检查输出: {result.output[:300]}"
        )

    print("[WARNING] 预构建环境检查失败，启用开发模式现场安装回退")
    _install_python_environment(backend)
    verify = backend.execute(
        f'{_VENV_PATH}/bin/python -c "{_IMPORT_CHECK}"', timeout=30
    )
    if verify.exit_code != 0:
        raise RuntimeError(f"沙箱 Python 依赖安装后仍不可用: {verify.output[:300]}")


def _install_python_environment(backend: OpenSandboxBackend) -> None:
    """现场创建 venv；仅供显式启用的开发回退使用。

    系统 Python 设置了 externally managed 限制（PEP 668），--system 安装会被拒绝。
    因此创建一个统一的 venv，并将 /opt/skills-venv/bin 注入 SANDBOX_PATH 最前面，
    所有 skill 的 python/pip 命令自动路由到 venv，无需改任何脚本。
    """
    # 1. 创建 venv（幂等：已存在则跳过）
    result = backend.execute(f"python3 -m venv {_VENV_PATH}")
    if result.exit_code != 0:
        print(f"[WARNING] venv 创建失败: {result.output[:200]}")
        raise RuntimeError(f"venv 创建失败: {result.output[:300]}")
    print(f"[INFO] Python venv 就绪: {_VENV_PATH}")

    # 2. 升级 pip（镜像加速，60s 超时）
    backend.execute(
        f"{_VENV_PIP} install --upgrade pip {_PIP_INSTALL_ARGS}", timeout=60
    )

    # 3. 预装依赖（sentinel 避免重复安装）
    for pkg in _PREINSTALL_PACKAGES:
        sentinel = f"/tmp/.venv_installed_{pkg}"
        check = backend.execute(f"test -f {sentinel}")
        if check.exit_code == 0:
            continue
        print(f"[INFO] 正在安装 Python 依赖: {pkg}...")
        result = None
        for attempt in range(1, 4):
            result = backend.execute(
                f"{_VENV_PIP} install {pkg} {_PIP_INSTALL_ARGS}",
                timeout=120,
            )
            if result.exit_code == 0:
                break
            print(
                f"[WARNING] {pkg} 第 {attempt}/3 次安装失败: "
                f"{result.output[:200]}"
            )
        if result.exit_code == 0:
            backend.execute(f"touch {sentinel}")
            print(f"[INFO]   {pkg} 安装成功")
        else:
            raise RuntimeError(
                f"{pkg} 安装失败（已重试 3 次）: {result.output[:300]}"
            )


def _seed_files(backend: OpenSandboxBackend) -> None:
    """
    将本地技能文件上传到沙箱。

    AGENTS.md 已迁移到 StoreBackend（全局共享，不经过沙箱）。
    仅上传在沙箱中尚不存在的文件，避免覆盖已更新的内容。
    """
    file_mapping: List[Tuple[Path, str]] = []

    # 遍历 skills 目录，添加所有技能文件
    skills_base = Path(LOCAL_SKILLS_DIR)
    if skills_base.exists():
        for skill_dir in skills_base.iterdir():
            if not skill_dir.is_dir():
                continue
            for local_file in skill_dir.rglob("*"):
                if local_file.is_file():
                    rel = local_file.relative_to(skills_base).as_posix()
                    sandbox_path = f"{SANDBOX_SKILLS_ROOT}/{rel}"
                    file_mapping.append((local_file, sandbox_path))

    # 收集需要上传的文件
    to_upload: List[Tuple[str, bytes]] = []
    for local_path, sandbox_path in file_mapping:
        if not local_path.exists():
            continue
        local_content = local_path.read_bytes()
        # 先用 test -f 检测，避免 download_files 对 404 输出 ERROR 日志。
        check = backend.execute(f"test -f {sandbox_path}")
        if check.exit_code == 0:
            try:
                results = backend.download_files([sandbox_path])
                if results and results[0].content and not results[0].error:
                    remote_content = results[0].content
                    if isinstance(remote_content, str):
                        remote_content = remote_content.encode("utf-8")
                    if remote_content == local_content:
                        continue
            except Exception:
                pass
        to_upload.append((sandbox_path, local_content))

    if to_upload:
        print(f"[INFO] 正在上传 {len(to_upload)} 个基础文件...")
        backend.upload_files(to_upload)
        print("[INFO] 基础文件上传完成。")
    else:
        print("[INFO] 所有基础文件已就绪，无需上传。")
