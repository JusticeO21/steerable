#!/usr/bin/env python3
"""Renders the template for each scope and fails on what copier exits on or
what a generated project would trip over: unrendered Jinja, broken doc links,
a collapsed CI gate list, or a backend-only repo that carries frontend files.

Runs copier as a module with absolute paths, so it behaves the same from cmd,
PowerShell, Git Bash and CI (the `copier` entry point cannot start prompt_toolkit
on a Git Bash console).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["PYTHONUTF8"] = "1"
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent
OUT = Path(tempfile.gettempdir()) / "bbp-render"

COMMON = {
    "project_name": "probe",
    "product_summary": "TODO: replace with 2-3 sentences. Name the user, the job the product does, and the single invariant that must never break.",
    "business_rules_source": "TODO: name the source of truth for business rules and how a rule is numbered (for example: product owner keeps BR-<AREA>-<NN> in the tracker).",
    "language": "TypeScript",
    "package_manager": "pnpm",
    "ui_stack": "React Router (Vite SPA)",
    "design_system": "Radix primitives + Tailwind CSS",
    "api_client_command": "pnpm gen:api",
    "frontend_language": "TypeScript",
    "backend_linter": "ruff",
    "backend_stack": "Python, FastAPI, Pydantic, SQLAlchemy 2.0 (async)",
    "worker_stack": "Celery, same codebase, separate process",
    "db_conventions": "snake-case-uuidv7",
    "backend_root": "src/backend",
    "frontend_root": "src/frontend",
    "migrations_root": "src/backend/migrations",
    "repo_layout": "",
    "tiering_hook": "docs/architecture/path-rules.md has a table.",
}

SCOPES = [
    ("full-stack", {"backend": "true", "frontend": "true"}, "served-by-this-repo"),
    ("frontend-only", {"backend": "false", "frontend": "true"}, "remote-schema"),
    ("backend-only", {"backend": "true", "frontend": "false"}, "remote-schema"),
]

LINK = re.compile(r"\]\((\.{0,2}/?[A-Za-z0-9./_-]+\.md)")
# A `${{ ... }}` expression is GitHub Actions syntax, not leftover Jinja.
JINJA = re.compile(r"(?<!\$)\{\{.*?\}\}|\{%.*?%\}|\{%.*$|%\}")

def copier_files() -> list[str]:
    """Every file path copier will walk. It renders each path, applies files
    whose name ends up empty, and never recurses into a directory whose rendered
    name is empty — so `src/{% if backend %}backend{% endif %}/...` silently
    generates nothing. Paths listed here still contain their own template."""
    files = []
    subdirectory = ROOT / "template"

    def walk(directory: Path, prefix: str) -> None:
        for entry in sorted(directory.iterdir()):
            if entry.name.startswith(".git"):
                continue
            rel = f"{prefix}{entry.name}"
            if entry.is_dir():
                walk(entry, rel + "/")
            elif entry.name.endswith(".jinja"):
                files.append(rel)

    walk(subdirectory, "")
    return files


def answer_blanks(answers: dict[str, str]) -> dict[str, str]:
    """`{% if backend %}` in a path copies a literal `{% if backend %}` into the
    path, which always renders truthy — the opposite of what the filename says."""
    out = {}
    for key, value in answers.items():
        if any(mark in value for mark in ("{%", "%}")):
            fail("template", f"answer {key} contains template syntax: {value[:40]}…")
        out[key] = value
    return out


status = 0


def fail(name: str, message: str) -> None:
    global status
    print(f"FAIL {name}: {message}")
    status = 1


def copier_python() -> str:
    """The interpreter that has copier: `uv tool`'s own, else `uvx --from copier`
    (cached after the first run). The `copier` entry point is avoided because it
    cannot start prompt_toolkit on a Git Bash console."""
    candidates = [
        Path(os.environ.get("APPDATA", "")) / "uv" / "tools" / "copier" / "Scripts" / "python.exe",
        Path(os.environ.get("APPDATA", "")) / "uv" / "tools" / "copier" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists() and subprocess.run([str(candidate), "-c", "import copier"], capture_output=True).returncode == 0:
            return str(candidate)
    uvx = shutil.which("uvx")
    if uvx:
        return uvx
    sys.exit("copier not found: install it with `uv tool install copier`")


def render(name: str, answers: dict[str, str]) -> Path | None:
    target = OUT / name
    shutil.rmtree(target, ignore_errors=True)
    args = dict(COMMON)
    args.update(answers)
    cmd = [copier_python()]
    if Path(cmd[0]).stem == "uvx":
        cmd += ["--from", "copier", "python", "-m", "copier", "copy"]
    else:
        cmd += ["-m", "copier", "copy"]
    cmd += ["--overwrite", "--defaults", "--trust", "--quiet"]
    for key, value in args.items():
        cmd += ["-d", f"{key}={value}"]
    result = subprocess.run([*cmd, str(ROOT), str(target)], stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if result.returncode != 0:
        fail(name, "copier exited non-zero")
        print("\n".join(result.stderr.strip().splitlines()[-5:]))
        return None
    return target


def check(target: Path, name: str, answers: dict[str, str]) -> None:
    problems = 0
    ignored = {".venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}
    files = [p for p in target.rglob("*") if p.is_file() and not ignored & set(p.relative_to(target).parts)]

    leftovers = [p for p in files if p.suffix in {".md", ".mjs", ".py", ".toml", ".yaml", ".yml", ".json"} and JINJA.search(p.read_text(encoding="utf-8"))]
    if leftovers:
        fail(name, "unrendered Jinja in:\n" + "\n".join(f"  {p.relative_to(target)}" for p in leftovers))
        problems += 1

    broken = []
    for page in files:
        if page.suffix != ".md":
            continue
        for link in LINK.findall(page.read_text(encoding="utf-8")):
            if not (page.parent / link).exists():
                broken.append(f"  {page.relative_to(target)} -> {link}")
    if broken:
        fail(name, "broken doc links:\n" + "\n".join(sorted(set(broken))))
        problems += 1

    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    block = agents.split("CI runs, in order", 1)[-1].split("**`", 1)[0]
    gates = len([line for line in block.splitlines() if re.match(r"^\s{2}\S", line)])
    if gates < 3:
        fail(name, f"CI gate list rendered {gates} indented lines; expected one gate per line")
        problems += 1

    if (target / "pyproject.toml").exists():
        pyproject = (target / "pyproject.toml").read_text(encoding="utf-8")
        for expected in ("[tool.ruff]", "[tool.mypy]", "[tool.pytest.ini_options]"):
            if expected not in pyproject:
                fail(name, f"{expected} missing from pyproject.toml")
                problems += 1
        for required in ("Makefile", ".pre-commit-config.yaml", ".python-version", ".github/workflows/verify.yml", "tools/check.py"):
            if not (target / required).exists():
                fail(name, f"{required} missing for a Python backend")
                problems += 1

    frontend_files = (
        "package.json",
        "eslint.config.mjs",
        "prettier.config.mjs",
        "tsconfig.json",
        "vitest.config.ts",
        "vite.config.ts",
        ".husky/pre-commit",
        "docs/architecture/frontend.verify.mjs",
        "src/frontend/src/pages/home/ui/HomePage.test.tsx",
    )
    frontend = answers.get("frontend") == "true"
    for required in frontend_files:
        if frontend != (target / required).exists():
            fail(name, f"{required} {'missing' if frontend else 'present'} for a {'frontend' if frontend else 'backend-only'} repo")
            problems += 1
    # A directory that only one stack owns must not appear in the other scope:
    # copier keeps an emptied directory, so a stray `src/backend/` looks like a
    # full-stack layout and sends agents to code that is not there.
    for owned, wanted in (("src/backend", answers.get("backend") == "true"), ("src/frontend", frontend)):
        if not wanted and (target / owned).exists():
            fail(name, f"{owned}/ exists in a scope that does not own it")
            problems += 1
    header = (target / ".header.json").read_text(encoding="utf-8")
    for declared in re.findall(r'"frontend_toolchain": \[([^\]]*)\]', header):
        for path in re.findall(r'"([^"]+)"', declared):
            if not (target / path).exists():
                fail(name, f".header.json frontend_toolchain names {path}, which is not in the repo")
                problems += 1
    for declared in re.findall(r'"backend_toolchain": \[([^\]]*)\]', header):
        for path in re.findall(r'"([^"]+)"', declared):
            if not (target / path).exists():
                fail(name, f".header.json backend_toolchain names {path}, which is not in the repo")
                problems += 1
    testing = (target / "docs/engineering/testing.md").read_text(encoding="utf-8")
    if "tests/backend/" in testing:
        fail(name, "testing.md still points at a top-level tests/backend/ directory")
        problems += 1

    if frontend:
        package = (target / "package.json").read_text(encoding="utf-8")
        for script in ('"check"', '"lint:fsd"', '"typecheck"', '"test":', '"format:check"'):
            if script not in package:
                fail(name, f"package.json has no {script} script")
                problems += 1

    if not problems:
        markers = sum(p.read_text(encoding="utf-8").count("CHECK:confirm") for p in files if p.suffix == ".md")
        print(f"OK   {name} ({len(files)} files, {markers} CHECK markers)")


PROVEN = {
    "docs/architecture/{% if backend %}backend.md{% endif %}.jinja",
    "docs/architecture/{% if backend %}database.md{% endif %}.jinja",
    "docs/architecture/{% if frontend %}frontend.md{% endif %}.jinja",
    "docs/architecture/{% if backend %}backend.verify.mjs{% endif %}.jinja",
    "docs/architecture/{% if frontend %}frontend.verify.mjs{% endif %}.jinja",
}


def check_layout() -> list[str]:
    """`{% if %}` in a file name is a feature. `{% if %}` in a directory name is
    not: it was proven word-for-word to make the file vanish, and the render
    reported success. Files stay in normal directories, or in a directory that
    only ever exists for one stack (`tools/`, `migrations/`)."""
    problems = []
    for path in copier_files():
        for part in path.split("/")[:-1]:
            if part.startswith("{%"):
                problems.append(f"{path} (nested under conditional directory `{part}`)")
    if not PROVEN <= set(copier_files()):
        for missing in sorted(PROVEN - set(copier_files())):
            problems.append(f"{missing} (known-conditional file disappeared)")
    return problems


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    layout = check_layout()
    if layout:
        print("FAIL layout: files copier will not generate or will misrender:")
        for line in layout:
            print(f"  {line}")
        return 1
    for name, answers, owner in SCOPES:
        rendered = answer_blanks({**answers, "api_types_owner": owner})
        target = render(name, rendered)
        if target is not None:
            check(target, name, rendered)
    return status


if __name__ == "__main__":
    sys.exit(main())
