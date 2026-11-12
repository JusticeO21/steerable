#!/usr/bin/env python3
"""Renders the frontend template and fails on what copier exits on or
what a generated project would trip over: unrendered Jinja, broken doc links,
a collapsed CI gate list, or a frontend repo with backend files.

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
    "ui_stack": "Vite + React SPA",
    "design_system": "Radix primitives + Tailwind CSS",
    "api_client_command": "pnpm gen:api",
    "frontend_language": "TypeScript",
    "frontend_root": ".",
    "frontend_source_root": "src",
    "repo_layout": "",
    "tiering_hook": "docs/architecture/path-rules.md has a table.",
}

SCOPES = [
    (
        "frontend",
        {
            "frontend": "true",
            "frontend_root": ".",
            "frontend_source_root": "src",
            "project_type": "frontend-only",
        },
    ),
]

LINK = re.compile(r"\]\((\.{0,2}/?[A-Za-z0-9./_-]+\.md)")
# A `${{ ... }}` expression is GitHub Actions syntax, not leftover Jinja.
# `{{ f"{{{x}}}" }}` in Python is one f-string brace, and `{{` in JSX is an
# object, so a doubled brace is not left-over Jinja.
JINJA = re.compile(r"(?<!\$)(?<!\{)\{\{(?!\{).*?(?<!\})\}\}(?!\})|\{%.*?%\}|\{%.*$|%\}")

def copier_files() -> list[str]:
    """Every file path copier will walk. It renders each path, applies files
    whose name ends up empty, and never recurses into a directory whose rendered
    name is empty. Paths listed here still contain their own template."""
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


def frontend(answers: dict[str, str]) -> bool:
    return answers.get("frontend") == "true"


# Frontend toolchain files written from the template without installing packages.
TOOLCHAIN = (
    "prettier.config.mjs",
    "playwright.config.ts",
    ".husky/pre-commit",
    ".editorconfig",
    ".prettierignore",
)
# Written by the first run of setup.py from its own definitions.
GENERATED = ("package.json", "eslint.config.mjs", "tsconfig.base.json", "tsconfig.json", "tsconfig.e2e.json", "vite.config.ts", "vitest.config.ts")


def generated_setup(target: Path) -> set[str]:
    """The generated names, read from the template-only setup script."""
    source = (ROOT / "template/src/frontend/setup.py").read_text(encoding="utf-8")
    names = re.findall(r'^    "([\w.]+)": "', source.split("CONFIGS = {", 1)[1], re.MULTILINE)
    return {*names, "package.json", "eslint.config.mjs"}


def answer_blanks(answers: dict[str, str]) -> dict[str, str]:
    """Reject answer strings that would be interpreted as template syntax."""
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
    source = Path(tempfile.mkdtemp(prefix="bbp-template-"))
    try:
        shutil.copy2(ROOT / "copier.yml", source / "copier.yml")
        shutil.copytree(
            ROOT / "template",
            source / "template",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        subprocess.run(["git", "init", "-q"], cwd=source, check=True)
        subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=source, check=True)
        subprocess.run(["git", "config", "user.name", "Template check"], cwd=source, check=True)
        subprocess.run(["git", "config", "user.email", "template-check@example.invalid"], cwd=source, check=True)
        subprocess.run(["git", "add", "copier.yml", "template"], cwd=source, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "template snapshot"], cwd=source, check=True)
    except Exception:
        shutil.rmtree(source)
        raise
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
    # Offline: the setup task writes the files and skips create-vite and the
    # package manager. The generated CI job renders with both.
    env = {
        **os.environ,
        "STEERABLE_NO_INSTALL": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        result = subprocess.run(
            [*cmd, str(source), str(target)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            fail(name, "copier exited non-zero")
            print("\n".join(result.stderr.strip().splitlines()[-5:]))
            return None
        return target
    finally:
        shutil.rmtree(source)


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

    has_frontend = frontend(answers)
    frontend_root = answers.get("frontend_root", "src/frontend")
    frontend_source_root = answers.get("frontend_source_root", frontend_root)
    frontend_files = (*TOOLCHAIN, "docs/architecture/frontend.verify.mjs")
    if has_frontend:
        written = generated_setup(target)
        for generated in GENERATED:
            if generated not in written:
                fail(name, f"setup.py writes no {generated}")
                problems += 1
            generated_path = target / generated if generated == "tsconfig.e2e.json" else target / frontend_root / generated
            if not generated_path.exists():
                fail(name, f"frontend setup did not generate {generated_path.relative_to(target)}")
                problems += 1
        if not (target / frontend_source_root / "app/index.tsx").exists():
            fail(name, f"frontend setup did not write the FSD app entry under {frontend_source_root}/app/index.tsx")
            problems += 1
        if (target / "src/frontend/setup.py").exists():
            fail(name, "frontend setup script leaked into the generated repository")
            problems += 1
        if (target / "src/frontend").exists():
            fail(name, "frontend-only output retained the src/frontend staging directory")
            problems += 1
        backend_artifacts = (
            "src/backend",
            "tools",
            "pyproject.toml",
            "Makefile",
            ".python-version",
            "docs/architecture/backend.md",
            "docs/architecture/database.md",
            "docs/architecture/backend.verify.mjs",
        )
        for artifact in backend_artifacts:
            if (target / artifact).exists():
                fail(name, f"frontend-only output contains backend artifact {artifact}")
                problems += 1
        for misplaced in ("app", "pages", "widgets", "features", "entities", "shared", "test-setup.ts"):
            if (target / misplaced).exists():
                fail(name, f"FSD source must live under src/, not repository-root/{misplaced}")
                problems += 1
        python_files = [p for p in files if p.suffix == ".py"]
        if python_files:
            fail(name, "frontend-only output contains Python files:\n" + "\n".join(f"  {p.relative_to(target)}" for p in python_files))
            problems += 1
        ignores = [p for p in files if p.name == ".gitignore"]
        if len(ignores) != 1 or ignores[0].relative_to(target).as_posix() != ".gitignore":
            fail(name, "frontend-only output should have one root .gitignore")
            problems += 1
        setup = ROOT / "template/src/frontend/setup.py"
        index = (target / "index.html").read_text(encoding="utf-8")
        if 'src="/src/app/index.tsx"' not in index:
            fail(name, "root index.html does not load /src/app/index.tsx")
            problems += 1
        rerun = subprocess.run(
            [sys.executable, str(setup), "--no-install"],
            cwd=target,
            capture_output=True,
            text=True,
        )
        if rerun.returncode != 0 or not (target / "src/app/index.tsx").exists():
            fail(name, "rerunning frontend setup did not preserve the root src/ app")
            if rerun.returncode != 0:
                print("\n".join(rerun.stderr.strip().splitlines()[-5:]))
            problems += 1
    for required in frontend_files:
        if has_frontend != (target / required).exists():
            fail(name, f"{required} {'missing' if has_frontend else 'present'} for a frontend repo")
            problems += 1
    header = (target / ".header.json").read_text(encoding="utf-8")
    if '"scope": "frontend-only"' not in header:
        fail(name, ".header.json does not declare a frontend-only project")
        problems += 1
    for path in ("src/backend", "src/frontend", "tools"):
        if (target / path).exists():
            fail(name, f"frontend-only output retained staging path {path}/")
            problems += 1
    generated = GENERATED if has_frontend else ()
    for declared in re.findall(r'"frontend_toolchain": \[([^\]]*)\]', header):
        for path in re.findall(r'"([^"]+)"', declared):
            if not (target / path).exists() and Path(path).name not in generated:
                fail(name, f".header.json frontend_toolchain names {path}, which is not in the repo")
                problems += 1
    if has_frontend:
        # The app comes from create-vite; the generator is template-only.
        for script in ("create_vite", "move_entry", "patch_index_html", "merge_package_json"):
            if f"def {script}(" not in (ROOT / "template/src/frontend/setup.py").read_text(encoding="utf-8"):
                fail(name, f"template/src/frontend/setup.py has no {script} step")
                problems += 1

    if not problems:
        markers = sum(p.read_text(encoding="utf-8").count("CHECK:confirm") for p in files if p.suffix == ".md")
        print(f"OK   {name} ({len(files)} files, {markers} CHECK markers)")


PROVEN = {
    "docs/architecture/{% if frontend %}frontend.md{% endif %}.jinja",
    "docs/architecture/{% if frontend %}frontend.verify.mjs{% endif %}.jinja",
}


def check_layout() -> list[str]:
    """`{% if %}` in a file name is a feature. `{% if %}` in a directory name is
    not: it was proven word-for-word to make the file vanish, and the render
    reported success. Files stay in normal directories, or in a directory that
    only ever exists for one stack."""
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
    for name, answers in SCOPES:
        rendered = answer_blanks(answers)
        target = render(name, rendered)
        if target is not None:
            check(target, name, rendered)
    return status


if __name__ == "__main__":
    sys.exit(main())
