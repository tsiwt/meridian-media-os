"""Build the submission zip deterministically and verify its contents."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "meridian-media-os-dp1024-submission.zip"
TOP = "meridian-media-os"
INCLUDE = ["app", "web", "docs", "samples", "tests", "tools", ".github"]
ROOT_FILES = [
    "README.md", "Dockerfile", "docker-compose.yml", "render.yaml", ".env.example",
    ".gitignore", ".dockerignore",
]
BLOCKED = {".db", ".db-wal", ".db-shm", ".pyc", ".log", ".zip", ".swp"}
BLOCKED_PARTS = {"__pycache__", ".git", "data", "node_modules", ".pytest_cache"}


def candidates():
    for name in ROOT_FILES:
        path = ROOT / name
        if path.is_file():
            yield path
    for folder in INCLUDE:
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if any(part in BLOCKED_PARTS for part in relative.parts):
                continue
            if path.suffix.lower() in BLOCKED or path.name.startswith("."):
                if path.name not in {".env.example", ".gitignore", ".dockerignore"}:
                    continue
            yield path


def main() -> None:
    files = list(candidates())
    output = OUTPUT.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, f"{TOP}/{path.relative_to(ROOT).as_posix()}")
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        bad = [
            name for name in names
            if name.endswith((".db", ".db-wal", ".db-shm", ".pyc", ".log", ".zip"))
            or "__pycache__" in name
            or "/data/" in name
            or "/.git/" in name
        ]
        assert not bad, f"blocked entries: {bad[:5]}"
        assert any(name.endswith("tests/test_core.py") for name in names)
        assert any(name.endswith("README.md") for name in names)
        print(f"zip={output}")
        print(f"entries={len(names)} size={output.stat().st_size} bad_entries={len(bad)}")


if __name__ == "__main__":
    main()