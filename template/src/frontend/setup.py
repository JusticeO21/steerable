#!/usr/bin/env python3
# steerable-checkout
"""Builds the frontend: Vite scaffolds the app shell, this script brings it
into Feature-Sliced Design.

    python <template>/src/frontend/setup.py [--check] [--no-install]
    copier update --trust

The template ships no React files of its own. `create-vite` writes the newest
Vite + React + TypeScript + ESLint starter, so a new project starts on current
tool versions instead of a snapshot. This script then:

  1. runs create-vite (skipped when src/frontend/app/index.tsx exists),
  2. moves the Vite entry point into the `app` layer and rewires index.html,
  3. deletes the starter's demo screen, prints every deleted file,
  4. writes the files Vite cannot know about: FSD slices, tests, configs,
  5. installs the extra packages with the chosen package manager, then merges
     the scripts into the package.json that install left behind.

`copier update` runs this script again when the file changes; an app that
already exists is kept, so a project's own code is never overwritten.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# The template-owned script runs with the generated repository as its cwd; it
# is never copied into the generated project.
HEADER = Path.cwd() / ".header.json"
CHECKOUT_MARK = "# steerable-checkout"


def header() -> dict:
    return json.loads(HEADER.read_text(encoding="utf-8"))


def answer(key: str, default: str) -> str:
    """An answer that is not rendered into this file (only paths and the
    copier version are): the setup task and every later run read them from
    .header.json."""
    return header().get("answers", {}).get(key) or default


PACKAGE_MANAGER = answer("package_manager", "pnpm")
FRONTEND_ROOT = answer("frontend_root", "src/frontend")
FRONTEND_SOURCE_ROOT = answer("frontend_source_root", FRONTEND_ROOT)
OPENAPI_SCHEMA = answer("openapi_schema", "./openapi.json")
UI_STACK = answer("ui_stack", "")
PROJECT = answer("project_name", Path.cwd().name)
APP = Path.cwd() / FRONTEND_ROOT
SRC = Path.cwd() / FRONTEND_SOURCE_ROOT
VITE_SRC = APP / "src"
SOURCE_REL = os.path.relpath(SRC, APP).replace(os.sep, "/")
SOURCE_PREFIX = "" if SOURCE_REL == "." else SOURCE_REL.rstrip("/") + "/"
VERIFY_SCRIPT = os.path.relpath(Path.cwd() / "docs/architecture/frontend.verify.mjs", APP).replace(os.sep, "/")
PRETTIER_IGNORE = os.path.relpath(Path.cwd() / ".prettierignore", APP).replace(os.sep, "/")

# Vite's starter, minus App.tsx, App.css and the demo images. Anything else
# create-vite writes stays; this script only adds to it.
DEMO_FILES = [
    "src/App.tsx",
    "src/App.css",
    "src/assets/hero.png",
    "src/assets/react.svg",
    "src/assets/vite.svg",
]

# Installed with `<pm> add` (no versions here): the package manager resolves
# the current releases within the starter's peer ranges.
DEV_PACKAGES = [
    "@eslint/js",
    "@playwright/test",
    "@testing-library/dom",
    "@testing-library/jest-dom",
    "@testing-library/react",
    "@testing-library/user-event",
    "@types/node",
    "eslint-import-resolver-typescript",
    "eslint-plugin-boundaries",
    "eslint-plugin-import",
    "eslint-plugin-jsx-a11y",
    "eslint-plugin-react",
    "eslint-plugin-react-hooks",
    "eslint-plugin-react-refresh",
    "globals",
    "husky",
    "jsdom",
    "lint-staged",
    "openapi-typescript",
    "prettier",
    "typescript-eslint",
    "vitest",
]
# Imported by the app, so they are runtime dependencies.
PACKAGES = [
    "@tanstack/react-query",
    "openapi-fetch",
    "react-hook-form",
    "zod",
]

SCRIPTS = {
    "format": f"prettier --write . --ignore-unknown --ignore-path {PRETTIER_IGNORE}",
    "format:check": f"prettier --check . --ignore-unknown --ignore-path {PRETTIER_IGNORE}",
    "lint": "eslint . --max-warnings=0",
    # `node <dir>/file` runs from this directory, so the verify script is
    # named relative to it.
    "lint:fsd": f"node {VERIFY_SCRIPT}",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test",
    "gen:api": f"openapi-typescript {OPENAPI_SCHEMA} -o {FRONTEND_SOURCE_ROOT}/shared/api/schema.d.ts",
    "check": (
        f"{PACKAGE_MANAGER} run format:check && {PACKAGE_MANAGER} run lint && "
        f"{PACKAGE_MANAGER} run lint:fsd && {PACKAGE_MANAGER} run typecheck && "
        f"{PACKAGE_MANAGER} run test"
    ),
}
LINT_STAGED = {
    "*.{ts,tsx}": ["prettier --write", "eslint --fix --max-warnings=0"],
    "*.{js,mjs,cjs,json,css,md,yml,yaml,html}": "prettier --write",
}

# create-vite's own configuration files are replaced, one config per tool, so
# no dead starter config is left behind. eslint.config.mjs is written by the
# template (it must agree with docs/architecture/frontend.md). package.json is
# kept: it holds the starter's dependencies, react and vite among them.
CREATE_VITE_CONFIGS = ["eslint.config.js", "vite.config.ts", "tsconfig.json"]
CONFIGS = {
    "vite.config.ts": """import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('{SRC_PATH}', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
})
""",
    "vitest.config.ts": """import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

// Tests are colocated with their slice (docs/engineering/testing.md):
// features/cancel-order/ui/CancelOrderButton.test.tsx
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('{SRC_PATH}', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['{SRC_PATH}/test-setup.ts'],
    include: ['{SRC_PATH}/**/*.{test,spec}.{ts,tsx}'],
    restoreMocks: true,
  },
})
""",
    "tsconfig.base.json": """{
  "compilerOptions": {
    "target": "es2023",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "esnext",
    "moduleResolution": "bundler",
    "moduleDetection": "force",
    "jsx": "react-jsx",
    "types": ["vite/client"],

    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "noImplicitReturns": true,
    "exactOptionalPropertyTypes": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true,
    "erasableSyntaxOnly": true,

    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "allowImportingTsExtensions": true,
    "allowArbitraryExtensions": true,
    "resolveJsonModule": true,

    "noEmit": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,

    "paths": {
      "@/*": ["{SRC_PATH}/*"]
    }
  }
}
""",
    # Playwright reads this tsconfig from the app directory. Playwright's own
    # config and e2e/ sit at the repository root and are checked by
    # tsconfig.e2e.json: tsc only walks down from the directory that holds a
    # config file, and does not check a config passed with --project.
    "tsconfig.json": """{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.tsbuildinfo",
    "types": ["vite/client", "node"]
  },
  "extends": "./tsconfig.base.json",
  "include": ["{SRC_PATH}/app", "{SRC_PATH}/pages", "{SRC_PATH}/widgets", "{SRC_PATH}/features", "{SRC_PATH}/entities", "{SRC_PATH}/shared", "{SRC_PATH}/test-setup.ts", "vite.config.ts", "vitest.config.ts"],
  "exclude": ["{SRC_PATH}/shared/api/schema.d.ts"]
}
""",
    # The e2e files sit at the repository root, but every package they import
    # (Playwright, @types/node) is installed in the app, because the app is
    # where the lockfile is. With no baseUrl (TypeScript 6 deprecates it),
    # typeRoots and paths resolve from this file, so both point down into the
    # app, and the paths value needs a leading `./`.
    "tsconfig.e2e.json": """{
  "compilerOptions": {
    "target": "es2023",
    "lib": ["es2023", "dom", "dom.iterable"],
    "module": "esnext",
    "moduleResolution": "bundler",
    "typeRoots": ["{FRONTEND_ROOT}/node_modules/@types"],
    "types": ["node"],
    "paths": {
      "@playwright/test": ["./{FRONTEND_ROOT}/node_modules/@playwright/test"]
    },
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true
  },
  "include": ["playwright.config.ts", "e2e"],
  "exclude": ["dist", "coverage", "playwright-report", "test-results"]
}
""",
}


def run(args: list[str], cwd: Path | None = None) -> bool:
    print(f"  $ {' '.join(args)}", flush=True)
    if os.name != "nt":
        return subprocess.run(args, cwd=cwd).returncode == 0
    # Windows starts a launcher only through a PATHEXT search (the shell) or by
    # full path: the list form looks for a file literally named "pnpm".
    return subprocess.run(args, cwd=cwd, shell=True).returncode == 0


def create_vite(target: Path) -> bool:
    if PACKAGE_MANAGER == "pnpm":
        scaffold = ["pnpm", "dlx", "create-vite@latest"]
    elif PACKAGE_MANAGER == "npm":
        scaffold = ["npx", "--yes", "create-vite@latest"]
    elif PACKAGE_MANAGER == "yarn":
        scaffold = ["yarn", "dlx", "create-vite@latest"]
    else:
        scaffold = ["bun", "x", "create-vite@latest"]
    # Scaffolds into a scratch directory inside the app, then moves the result
    # up: `--overwrite` means *remove existing files*, so aiming it at the app
    # deletes setup.py and the lint config sitting next to it. The app dir is
    # where pnpm's `dlx` looks for a package.json down from the working
    # directory; --no-interactive takes the defaults for any flag.
    scratch = target / ".create-vite"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir()
    run(
        scaffold + [".create-vite", "--template", "react-ts", "--eslint", "--no-interactive", "--overwrite"],
        cwd=target,
    )
    for entry in list(scratch.iterdir()):
        dest = target / entry.name
        if dest.is_dir():
            shutil.rmtree(dest, ignore_errors=True)
        elif dest.exists():
            dest.unlink()
        entry.replace(dest)
    scratch.rmdir()
    # A missing gate file means the scaffold cancelled (a refusal exits 0).
    return (APP / "package.json").exists()


def move_entry() -> None:
    main = VITE_SRC / "main.tsx"
    if main.exists():
        (SRC / "app").mkdir(parents=True, exist_ok=True)
        shutil.copy2(main, SRC / "app" / "index.tsx")
        main.unlink()


def patch_index_html() -> None:
    html = APP / "index.html"
    if not html.exists():
        write(
            html,
            """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{PROJECT}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""".replace("{PROJECT}", PROJECT).replace("{SOURCE_PREFIX}", SOURCE_PREFIX),
        )
    text = html.read_text(encoding="utf-8")
    text = re.sub(r"(<title>)(.*?)(</title>)", rf"\g<1>{PROJECT}\g<3>", text)
    entry = f"/{SOURCE_PREFIX}app/index.tsx"
    text = text.replace('src="/src/main.tsx"', f'src="{entry}"')
    text = text.replace('src="/src/app/index.tsx"', f'src="{entry}"')
    if SOURCE_PREFIX:
        text = text.replace('src="/app/index.tsx"', f'src="{entry}"')
    html.write_text(text, encoding="utf-8")


def prune_demo() -> None:
    for name in DEMO_FILES:
        path = APP / name
        if path.is_file():
            path.unlink()
            print(f"    deleted {FRONTEND_ROOT}/{name}")
    assets = VITE_SRC / "assets"
    if assets.is_dir() and not any(assets.iterdir()):
        assets.rmdir()


LINT_CONFIG = APP / "eslint.config.mjs"


def apply_lint_config() -> int:
    """Move Copier's rendered staging config to the standalone app root."""
    staged = Path.cwd() / "src/frontend/eslint.config.mjs"
    if staged.is_file():
        write(LINT_CONFIG, substitute(staged.read_text(encoding="utf-8")))
        return 0
    if LINT_CONFIG.is_file():
        return 0
    here = Path(os.environ.get("STEERABLE_SETUP_SOURCE", Path(__file__).parent))
    for name in ("eslint.config.mjs", "eslint.config.mjs.jinja"):
        source = here / name
        if source.is_file():
            text = source.read_text(encoding="utf-8")
            # Offline (STEERABLE_NO_INSTALL) copier leaves it unrendered.
            if "{{" in text:
                write(APP / ".eslint.config.mjs.template", text)
            else:
                write(LINT_CONFIG, substitute(text))
            return 0
    print("FAIL: no eslint config next to setup.py (expected eslint.config.mjs[.jinja])")
    return 1


def substitute(text: str) -> str:
    # Constants are substituted by hand, not with an f-string: a TS template
    # nests braces (`{ '@': ... }`), which an f-string reads as expressions.
    # {SRC_PATH} is the app's source root as seen from its own directory.
    return (
        text.replace("{SOURCE_PREFIX}", SOURCE_PREFIX)
        .replace(
            "{SRC_PATH}",
            "." if os.path.relpath(SRC, APP) == "." else "./" + os.path.relpath(SRC, APP).replace(os.sep, "/"),
        )
        .replace("{FRONTEND_ROOT}", FRONTEND_ROOT)
        .replace("{PACKAGE_MANAGER}", PACKAGE_MANAGER)
    )


def apply_configs() -> None:
    for name in CREATE_VITE_CONFIGS:
        (APP / name).unlink(missing_ok=True)
    for name in ("tsconfig.app.json", "tsconfig.node.json"):
        (APP / name).unlink(missing_ok=True)
    for name, text in CONFIGS.items():
        base = Path.cwd() if name.startswith("tsconfig.e2e") else APP
        (base / name).write_text(substitute(text), encoding="utf-8", newline="\n")


def record(ui_stack: str) -> None:
    # Facts an agent would otherwise have to guess: which generator produced
    # the app and what the generator cannot answer. Kept next to the template
    # source in .header.json, which copier update merges.
    data = header()
    data.setdefault("frontend", {})
    data["frontend"].update({"generator": "create-vite react-ts --eslint", "ui_stack": ui_stack})
    HEADER.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_files() -> None:
    # Index.tsx keeps the Vite entry point (StrictMode, createRoot) and mounts
    # the router; it holds no markup of its own.
    write(
        SRC / "app" / "index.tsx",
        """import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { Router } from './router'
import './styles/global.css'

const container = document.getElementById('root')
if (!container) throw new Error('#root is missing from index.html')

createRoot(container).render(
  <StrictMode>
    <Router />
  </StrictMode>,
)
""",
    )
    write(
        SRC / "app" / "router" / "Router.tsx",
        """import { HomePage } from '@/pages/home'

// Route table: pages/ is imported here and nowhere else. Add a router
// (React Router, TanStack Router) as an ADR decision; until then the app has
// one screen. Pages are lazy-loaded once there is more than one.
export function Router() {
  return <HomePage />
}
""",
    )
    write(SRC / "app" / "router" / "index.ts", "export { Router } from './Router'\n")
    # create-vite's index.css is the global stylesheet: the app layer owns it.
    index_css = VITE_SRC / "index.css"
    if index_css.exists():
        (SRC / "app" / "styles").mkdir(parents=True, exist_ok=True)
        shutil.move(str(index_css), str(SRC / "app" / "styles" / "global.css"))

    write(
        SRC / "pages" / "home" / "model" / "content.ts",
        """// Every string the home page renders. JSX reads from here, never from a
// literal (docs/architecture/frontend.md#content-and-internationalization).
export const homeContent = {
  title: {title},
  subtitle: 'The app shell is running. Replace this page with the first screen.',
  action: 'Get started',
} as const
""".replace("{title}", json.dumps(PROJECT, ensure_ascii=False)),
    )
    write(
        SRC / "pages" / "home" / "ui" / "HomePage.tsx",
        """import { Button } from '@/shared/ui/Button'

import { homeContent } from '../model/content'

export function HomePage() {
  return (
    <main>
      <h1>{homeContent.title}</h1>
      <p>{homeContent.subtitle}</p>
      <Button>{homeContent.action}</Button>
    </main>
  )
}
""",
    )
    write(
        SRC / "pages" / "home" / "ui" / "HomePage.test.tsx",
        """import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { homeContent } from '../model/content'
import { HomePage } from './HomePage'

describe('HomePage', () => {
  it('renders its heading and action from the content module', () => {
    render(<HomePage />)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(homeContent.title)
    expect(screen.getByRole('button', { name: homeContent.action })).toBeInTheDocument()
  })
})
""",
    )
    write(SRC / "pages" / "home" / "index.ts", "export { HomePage } from './ui/HomePage'\n")
    write(
        SRC / "shared" / "ui" / "Button.tsx",
        """import type { ComponentProps } from 'react'

// Accessible primitive: a real <button>, so keyboard and focus behaviour come
// from the platform. Features style it; they do not re-implement it.
export function Button({ className, type = 'button', ...props }: ComponentProps<'button'>) {
  return <button type={type} className={className} {...props} />
}
""",
    )
    write(SRC / "shared" / "ui" / "index.ts", "export { Button } from './Button'\n")
    write(
        SRC / "test-setup.ts",
        """import '@testing-library/jest-dom/vitest'

// Every component test renders into jsdom; nothing here talks to the network.
// Mock HTTP at the shared/api seam with MSW (docs/engineering/testing.md).
""",
    )
    # One repository-level ignore file covers the generated frontend app.
    write(
        Path.cwd() / ".gitignore",
        """node_modules/
dist/
coverage/
playwright-report/
test-results/
*.tsbuildinfo
""",
    )
    docs_frontend = os.path.relpath(Path.cwd() / "docs/architecture/frontend.md", APP).replace(os.sep, "/")
    app_title = "Frontend" if FRONTEND_ROOT == "." else FRONTEND_ROOT
    write(
        APP / "README.md",
        substitute(
            f"""# {app_title} - Feature-Sliced Design app

See [frontend architecture]({docs_frontend}) for the
layer, slice, segment, and public-API rules. Three tools enforce them:

| Command | What it checks |
|---|---|
| `{PACKAGE_MANAGER} lint` | ESLint: types-aware rules, React, a11y, layer imports |
| `{PACKAGE_MANAGER} lint:fsd` | `docs/architecture/frontend.verify.mjs` (structure) then ESLint |
| `{PACKAGE_MANAGER} check` | everything CI runs: format, lint, FSD, types, tests |

Copier generated this app with Vite and adapted its entry point into `app/`.
Run `copier update --trust` from the repository root for template updates.

```
{FRONTEND_SOURCE_ROOT}/
  index.html                    # Vite entry
  app/index.tsx                 # composition root: mounts pages, wires providers
  app/styles/global.css         # global CSS and design tokens
  pages/
      home/                     # a slice: one route-level screen
        ui/HomePage.tsx
        ui/HomePage.test.tsx    # colocated test
        model/content.ts        # every user-visible string this page renders
        index.ts                # the slice's public API
  widgets/  features/  entities/  # add slices here as the product grows
  shared/                       # business-agnostic: ui, api, lib, config, i18n
  test-setup.ts                 # Vitest setup, imported by vitest.config.ts
```

`pages/home/` is a reference slice, not a recommendation: it exists so every
gate has something real to check on the first commit. Replace it with the first
real screen.

Rules no tool can check, and that review must: name slices with domain terms
from `docs/product/business-rules.md`; promote code down a layer only when a
second consumer appears; keep business rules out of components.
"""
        ),
    )


def merge_package_json() -> None:
    package_file = APP / "package.json"
    package = json.loads(package_file.read_text(encoding="utf-8")) if package_file.exists() else {}
    scripts = package.get("scripts", {})
    scripts["dev"] = "vite"
    scripts["build"] = "tsc --noEmit && vite build"
    scripts["preview"] = "vite preview"
    scripts.update({key: substitute(value) for key, value in SCRIPTS.items()})
    # One tsconfig per project: tsconfig.json owns the app, tsconfig.e2e.json
    # owns playwright.config.ts and e2e/. Scripts run inside the app, so the
    # second path is relative to it.
    e2e = os.path.relpath(Path.cwd() / "tsconfig.e2e.json", APP).replace(os.sep, "/")
    scripts["typecheck"] = f"tsc --noEmit && tsc --noEmit -p {e2e}"
    package["name"] = PROJECT
    package["scripts"] = scripts
    package["lint-staged"] = LINT_STAGED
    package_file.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")


def install_packages() -> bool:
    manager = {
        "pnpm": "pnpm",
        "npm": "npm",
        "yarn": "yarn",
        "bun": "bun",
    }[PACKAGE_MANAGER]
    # `yarn add` (no install) and `yarn install` are both valid; the others need
    # a different verb to install rather than add.
    install = "install" if manager == "npm" else "add"
    # A run that did not scaffold (no create-vite, e.g. a retry offline) has no
    # starter dependencies yet: install those first or they never arrive.
    run([manager, "install"], cwd=APP)
    dev = run([manager, install, "--save-dev", *DEV_PACKAGES], cwd=APP)
    return run([manager, install, *PACKAGES], cwd=APP) and dev


def check() -> int:
    package = json.loads((APP / "package.json").read_text(encoding="utf-8"))
    missing = [
        name
        for name in ("dev", "build", "lint", "typecheck", "test", "check")
        if name not in package["scripts"]
    ]
    for name in missing:
        print(f"FAIL {FRONTEND_ROOT}: package.json has no {name} script")
    return 1 if missing else 0


def main(argv: list[str]) -> int:
    # Only the template's own copy runs; the stub below hands the work to
    # `setup.py.running`. This test only reads the file, so a copy passes it
    # and would nest the app (the marker sits below copier's trailer).
    if os.environ.get("STEERABLE_LAUNCHED") != "1" and not Path(__file__).read_text(
        encoding="utf-8"
    ).startswith(f"#!/usr/bin/env python3\n{CHECKOUT_MARK}\n"):
        sys.exit(
            f"setup.py in {Path(__file__).parent} is a copy, not the template's; "
            "run the template's src/frontend/setup.py."
        )
    if "--check" in argv:
        return check()
    # STEERABLE_NO_INSTALL is how an offline render (CI, check-template.py)
    # proves the files without a network round trip.
    offline = "--no-install" in argv or os.environ.get("STEERABLE_NO_INSTALL") == "1"
    # The check above only reads the template's copy, so a copy inside the app
    # passes it. As a subprocess it moves aside while it writes; the copier
    # task runs it from the root. `python setup.py` in the app is a copy.
    if os.environ.get("STEERABLE_LAUNCHED") != "1" and Path.cwd() == Path(__file__).parent:
        sys.exit("run this script from the generated repository root, not from its own directory")
    # Copier updates can bring an existing v2 app from the previous nested
    # layout. Move its FSD layers up one level before deciding whether to
    # scaffold, preserving every existing module.
    legacy_src = APP / "src"
    if APP == SRC and (legacy_src / "app" / "index.tsx").exists() and not (APP / "app" / "index.tsx").exists():
        conflicts = [p.name for p in legacy_src.iterdir() if (APP / p.name).exists()]
        if conflicts:
            sys.exit(f"cannot flatten legacy frontend src/: destination paths already exist: {', '.join(conflicts)}")
        for entry in list(legacy_src.iterdir()):
            entry.replace(APP / entry.name)
        legacy_src.rmdir()
    fresh = not (SRC / "app" / "index.tsx").exists()
    lint = 0
    if fresh:
        APP.mkdir(parents=True, exist_ok=True)
        # A package.json without the app is the one create-vite leaves behind
        # when it finished and this script did not; scaffolding again is safe.
        if not offline:
            print(f"create-vite: writing a new app into {FRONTEND_ROOT}/", flush=True)
            if not create_vite(APP):
                print("create-vite failed; run this script again once the network works")
                return 1
    if fresh or (VITE_SRC / "main.tsx").exists():
        # Copies the entry point instead of moving it, so a rerun is harmless.
        move_entry()
        patch_index_html()
        prune_demo()
        apply_configs()
        lint = apply_lint_config()
        write_files()
        if VITE_SRC.is_dir():
            if VITE_SRC == SRC:
                allowed = {
                    "app", "pages", "widgets", "features", "entities", "shared", "test-setup.ts",
                    "frontend",
                }
                remaining = [p for p in VITE_SRC.iterdir() if p.name not in allowed]
            else:
                remaining = list(VITE_SRC.iterdir())
            if remaining:
                print("FAIL: unexpected create-vite files remain under src/: " + ", ".join(p.name for p in remaining))
                return 1
            if VITE_SRC != SRC:
                VITE_SRC.rmdir()
        record(UI_STACK)
        if not offline:
            install_packages()
        # After the installs: `add` rewrites package.json compactly and drops
        # the scripts and lint-staged this merge adds.
        merge_package_json()
        if not offline:
            # Prettier-check is the first CI gate; the files written above are
            # not in its style until this runs (it needs the installed prettier).
            prettier = APP / "node_modules" / ".bin" / ("prettier.CMD" if os.name == "nt" else "prettier")
            if prettier.exists():
                run([os.fspath(prettier), "--write", ".", "--ignore-unknown", "--ignore-path", PRETTIER_IGNORE], cwd=APP)
        print("frontend scaffolded from create-vite and adapted to FSD")
    else:
        lint = apply_lint_config()
        apply_configs()
        patch_index_html()
        write_files()
        record(header().get("frontend", {}).get("ui_stack") or UI_STACK)
        merge_package_json()
        prettier = APP / "node_modules" / ".bin" / ("prettier.CMD" if os.name == "nt" else "prettier")
        if prettier.exists():
            owned = [
                "eslint.config.mjs", "index.html", "package.json", "tsconfig.base.json", "tsconfig.json",
                "vite.config.ts", "vitest.config.ts", "app/index.tsx",
                "app/router/Router.tsx", "app/router/index.ts", "app/styles/global.css",
                "pages/home/model/content.ts", "pages/home/ui/HomePage.tsx",
                "pages/home/ui/HomePage.test.tsx", "pages/home/index.ts",
                "shared/ui/Button.tsx", "shared/ui/index.ts", "test-setup.ts",
            ]
            run([os.fspath(prettier), "--write", *[path for path in owned if (APP / path).exists()]], cwd=APP)
        print(f"{FRONTEND_ROOT}/app kept; regenerated the files this script owns")
    return lint


if __name__ == "__main__":
    # A subprocess finishes with this file still open, and Windows closes it
    # last: a second process that rewrites it (tempdir's cleanup right after
    # the task) hits this one. Copy to `setup.py.running` and run the copy;
    # the process holds only the copy, and the next run checks which copy it
    # is with STEERABLE_LAUNCHED.
    running = Path.cwd() / ".steerable-setup.running.py"
    if os.environ.get("STEERABLE_LAUNCHED") == "1":
        if running.exists():
            running.unlink()
        sys.exit(main(sys.argv[1:]))
    shutil.copy2(Path(__file__), running)
    try:
        # --no-install still carries through; nothing else is needed.
        env = os.environ | {
            "STEERABLE_LAUNCHED": "1",
            "STEERABLE_SETUP_SOURCE": str(Path(__file__).parent),
        }
        sys.exit(subprocess.run([sys.executable, str(running), *sys.argv[1:]], env=env).returncode)
    finally:
        running.unlink(missing_ok=True)
