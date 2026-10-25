"""Versioned prompt files: <name>.<version>.md. To change a prompt, add a new version file and point VERSIONS at
it; the version is stored with every call in llm_calls, so results can be compared per prompt version."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent
VERSIONS = {"extraction": "v2", "phrasing": "v1", "explanation": "v1"}


@dataclass(frozen=True)
class Prompt:
    version: str  # e.g. extraction.v1
    text: str


@lru_cache
def load(name: str) -> Prompt:
    version = f"{name}.{VERSIONS[name]}"
    return Prompt(version, (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8").strip())
