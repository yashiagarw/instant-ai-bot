"""backend/engine must stay plain Python: no web framework or app imports (CLAUDE.md)."""

import ast
import importlib
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine"
FORBIDDEN = ("fastapi", "starlette", "uvicorn", "app")


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_engine_is_importable():
    assert importlib.import_module("engine")


def test_engine_has_no_web_imports():
    for path in ENGINE.rglob("*.py"):
        bad = imported_modules(path) & set(FORBIDDEN)
        assert not bad, f"{path.name} imports {bad}"


def test_module_folders_exist():
    for name in ("vehicles", "knowledge", "diagnosis", "requests"):
        assert importlib.import_module(f"app.{name}")
