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
# render into a new directory
uvx copier copy --trust gh:<owner>/<this-repo> my-project

# or from a local clone
uvx copier copy --trust ./path/to/this-repo my-project
```

Run interactively; the questions decide the scope and the commands written into
the docs. To accept every default (used by the template's own tests):

```bash
uvx copier copy --trust --defaults . my-project
```

Then, inside the generated repository, run the setup command written in
`AGENTS.md` (the `tools.setup` field in `.header.json` holds the same string).
Create or clone the git repository first: the frontend setup installs husky
hooks, which need a git work tree.

```bash
uv sync --all-groups && uv run pre-commit install   # backend and full stack
pnpm install                                        # frontend and full stack
```

Open `AGENTS.md` and complete "START HERE". The docs use `CHECK:confirm` markers
for facts only the project can know, such as the real source of business rules.

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
