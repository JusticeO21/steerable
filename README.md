# steerable

Steerable is a [copier](https://copier.readthedocs.io/) template for a
repository an AI agent can work in without drifting: `AGENTS.md` and `docs/`
hold the same rules for every project, the docs say which rule applies to which
path, and the toolchain for each stack is already wired into lint, pre-commit,
and CI.

The template enforces **structure** (folders, layer boundaries, lint rules, test
naming, ADR process). It does not choose **strategy** (framework, ORM, store,
auth, queue); a choice between viable alternatives is recorded as an ADR in the
generated repository.

## What you get

| Scope | Toolchain generated |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, `ruff`, `mypy --strict`, `pytest`, `pre-commit`, boundary checker, ADR drift check, GitHub Actions |
| Frontend | TypeScript strict, Vite + React Router (or Next.js), ESLint (flat config + Feature-Sliced Design boundaries), Prettier, Vitest + Testing Library, Playwright config, husky + lint-staged |

Every scope gets `AGENTS.md` and pointer files (`CLAUDE.md`, `Gemini.md`,
`.qoder/rules.md`, `.github/copilot-instructions.md`), `docs/` (architecture,
product rules, engineering standards, ADR scaffolding), and `.header.json`
describing the generated repository to agents.

## Requirements

- [uv](https://docs.astral.sh/uv/) for a backend scope
- Node.js 20+ and the chosen package manager for a frontend scope

## Use it

```bash
# new project, asked interactively
uvx copier copy --trust gh:JusticeO21/steerable my-project
```

The first two questions decide the scope; everything else has a default that
`Enter` accepts.

```
🎤 Does this repository contain a backend (API, database, workers)? [y/n]
🎤 Does this repository contain a web frontend? [y/n]
🎤 Package manager
   pnpm
 > npm
   yarn
   bun
```

To skip the prompts, pass the answers. The scope is the only thing worth
deciding up front:

```bash
# full stack: FastAPI backend + Vite/React frontend
uvx copier copy --trust gh:JusticeO21/steerable shop \
  -d backend=true -d frontend=true -d project_name=shop

# API only: no package.json, no eslint, no husky
uvx copier copy --trust gh:JusticeO21/steerable shop-api \
  -d backend=true -d frontend=false

# web client only: calls an API served elsewhere
uvx copier copy --trust gh:JusticeO21/steerable shop-web \
  -d backend=false -d frontend=true
```

### Full walkthrough (full stack)

```bash
uvx copier copy --trust gh:JusticeO21/steerable shop -d project_name=shop
cd shop
git init                # husky needs a work tree
pnpm install            # frontend deps, then installs the husky hook
uv sync --all-groups    # backend deps

pnpm dev                                       # http://localhost:5173
uv run uvicorn backend.app.main:app --reload   # http://localhost:8000
```

The husky hook formats and lints staged frontend files on every commit. In a
full-stack or frontend repo it owns the git hook, so `pre-commit install` is
not run (it would replace it); backend and docs gates come from `make check`
and CI. A backend-only repo has no husky, so setup runs
`pre-commit install` instead.

`make help` (or the `scripts` block in `package.json`) lists the rest:

```bash
make check     # everything CI runs
make test      # pytest
make fmt       # ruff format
make lint      # ruff check
pnpm run check # frontend: prettier, eslint, FSD, tsc, vitest
pnpm test      # vitest only
```

### What lands in the repository

```
shop/
  AGENTS.md                  rules every agent reads first, plus "START HERE"
  CLAUDE.md, Gemini.md, .qoder/rules.md, .github/copilot-instructions.md
  .header.json               commands, paths, and sources, for agents
  docs/
    architecture/            overview, path-rules table, backend, database,
                             frontend, security, backend.verify.mjs
    architecture/decisions/  ADR-000 template + drift check
    product/business-rules.md   BR-<AREA>-<NN>, cited by tests
    engineering/             testing.md, code-review.md
  src/backend/
    app/modules/orders/      router.py, service.py, repository.py
    tests/
  src/frontend/src/
    app/ pages/home/ shared/ui/
  tools/check.py             runs every backend and docs gate
  .github/workflows/verify.yml
```

An agent opening `shop/` reads `AGENTS.md`, which points it at
`docs/architecture/path-rules.md` ("which rules apply to this path") and at the
business rules it must not break. Before the first edit it runs the "START
HERE" checks and replaces the `CHECK:confirm` and `TODO: replace` markers —
those are the facts only your project knows, such as where rule IDs come from
and the one invariant the product must never break.

### Wiring it into an existing repository

`copier copy` writes into a directory. For an existing checkout, use
`copier apply` with the answers file, or copy into the existing tree:

```bash
uvx copier copy --trust gh:JusticeO21/steerable . -d backend=true -d frontend=false
```

Conflicting files are reported and left untouched unless you pass
`--overwrite`; review each report rather than accepting all of them.

## Update an existing repository

Templates evolve. Re-render to pull fixes without losing local work:

```bash
uvx copier update --trust
```

Copier three-way-merges the template diff against your changes and records the
answers in `.copier-answers.yml`, so commit that file.

## Maintain it

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add a question, a document, or
a check, and the naming trap that silently drops generated files.

```bash
python check-template.py
```

renders all three scopes with copier and fails on unrendered Jinja, broken doc
links, a collapsed CI gate list, and files appearing in the wrong scope.

## License

[MIT](LICENSE)
