"""Environment settings shared by live and local modes."""

import os
from pathlib import Path


def data_dir() -> Path:
    path = Path(os.getenv("ASU_DATA_DIR", ".local/asu")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path(name: str) -> Path:
    return data_dir() / f"{name}.sqlite3"


def validate_live_settings() -> None:
    missing = []
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key or key.startswith("replace-"):
        missing.append("DEEPSEEK_API_KEY")
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret) < 32 or secret.startswith("replace-"):
        missing.append("JWT_SECRET_KEY (at least 32 random characters)")
    if missing:
        raise RuntimeError(
            "Live mode requires " + ", ".join(missing)
            + ". Use python start_all.py --mode demo for the synthetic local demo."
        )
