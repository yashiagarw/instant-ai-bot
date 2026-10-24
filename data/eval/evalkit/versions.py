"""Engine versions: the working tree ("current"), a git ref (commit, tag, branch) or a folder.

A git ref is extracted with `git archive` into a temporary folder and run in its own process, with that folder
first on sys.path, so two versions never share the `engine` package. The knowledge loader and the database are
always today's; an engine version must accept today's knowledge (fields it lacks are dropped by the loader).
"""

from __future__ import annotations

import hashlib
import subprocess
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CURRENT = "current"


class VersionError(ValueError):
    pass


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout.strip()


def engine_hash(engine_dir: Path) -> str:
    """Short hash of the engine's Python files: tells versions apart even when ENGINE_VERSION was not bumped."""
    h = hashlib.sha1()
    for path in sorted(engine_dir.glob("*.py")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:10]


def git_info() -> dict:
    try:
        return {
            "git_commit": git("rev-parse", "--short", "HEAD"),
            "git_dirty": bool(git("status", "--porcelain", "--", "backend/engine")),
        }
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"git_commit": "unknown", "git_dirty": False}


def materialise(spec: str, workdir: Path | None = None) -> Path | None:
    """A folder whose `engine/` subfolder is the engine to run; None for the working tree."""
    if spec == CURRENT:
        return None
    path = Path(spec)
    if path.is_dir():
        if (path / "engine" / "core.py").is_file():
            return path.resolve()
        if (path / "core.py").is_file() and path.name == "engine":
            return path.parent.resolve()
        raise VersionError(f"{spec}: no engine/core.py in this folder")
    try:
        commit = git("rev-parse", "--verify", "--quiet", f"{spec}^{{commit}}")
    except subprocess.CalledProcessError as e:
        raise VersionError(f"{spec}: not a folder or a git commit, tag or branch") from e
    out = Path(workdir or tempfile.mkdtemp(prefix="engine-")) / commit[:10]
    if not (out / "engine" / "core.py").is_file():
        data = subprocess.run(
            ["git", "-C", str(ROOT), "archive", "--format=tar", commit, "backend/engine"],
            check=True,
            capture_output=True,
        ).stdout
        with tarfile.open(fileobj=BytesIO(data)) as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.startswith("backend/engine/"):
                    member.name = member.name.removeprefix("backend/")
                    tar.extract(member, out, filter="data")
        if not (out / "engine" / "core.py").is_file():
            raise VersionError(f"{spec}: commit {commit[:10]} has no backend/engine/core.py")
    return out
