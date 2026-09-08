"""Local versioned prompts; a bad or missing release never silently changes text."""

import hashlib
import os
from pathlib import Path

_PROMPTS = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> tuple[str, str]:
    if name not in {"main", "researcher", "reviewer"}:
        raise ValueError("Unknown prompt")
    release = os.getenv("ASU_PROMPT_RELEASE", "v1")
    if release not in {"v1"}:
        raise ValueError(f"Unknown prompt release: {release}")
    text = (_PROMPTS / release / f"{name}.md").read_text(encoding="utf-8")
    return text, f"{release}:{hashlib.sha256(text.encode()).hexdigest()[:12]}"
