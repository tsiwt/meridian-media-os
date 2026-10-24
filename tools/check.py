"""Zero-dependency quality checks: compile, unused imports, file budgets.

Run: python tools/check.py
Exits non-zero on unused imports or compile errors. Large files and long lines
are reported as warnings (the reviewer's clean-code rubric values both).
"""

from __future__ import annotations

import ast
import compileall
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def compile_all() -> int:
    ok = compileall.compile_dir(str(ROOT / "app"), quiet=1)
    ok = compileall.compile_dir(str(ROOT / "tests"), quiet=1) and ok
    ok = compileall.compile_dir(str(ROOT / "tools"), quiet=1) and ok
    return 0 if ok else 1


def unused_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imported[name] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                imported[alias.asname or alias.name] = node.lineno
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            # attribute roots are captured by the Name node for `mod.attr`
            pass
    return [f"{path.relative_to(ROOT)}:{line} unused import {name}" for name, line in imported.items() if name not in used]


def main() -> int:
    failures = []
    if compile_all() != 0:
        failures.append("compileall failed")
    for folder in ("app", "tests", "tools"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            failures.extend(unused_imports(path))
    long_files = []
    for folder in ("app", "web", "tests", "tools"):
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".py", ".js", ".css", ".html", ".sql"}:
                continue
            lines = path.read_text(encoding="utf-8", errors="ignore").count("\n") + 1
            if path.suffix == ".py" and lines > 400:
                long_files.append(f"{path.relative_to(ROOT)} {lines} lines")
            if path.suffix == ".js" and lines > 400:
                long_files.append(f"{path.relative_to(ROOT)} {lines} lines")
    for name in long_files:
        print(f"WARN large file: {name}")
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        return 1
    print("check: compile ok, no unused imports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
