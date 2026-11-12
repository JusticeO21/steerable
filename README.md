# steerable

Steerable is a [copier](https://copier.readthedocs.io/) template for standalone
frontend repositories. It generates a Vite + React + TypeScript application at
the project root, with Feature-Sliced Design source under `src/`.

The template enforces **structure** (folders, layer boundaries, lint rules, test
naming, ADR process). It does not choose **product strategy**; decisions between
viable alternatives are recorded as ADRs in the generated repository.

Generated projects get strict TypeScript, Vite + React, ESLint with
Feature-Sliced Design boundaries, Prettier, Vitest + Testing Library,
Playwright configuration, Husky + lint-staged, `AGENTS.md`, and project
architecture and engineering docs.

## Requirements

- Node.js 20+ and a supported package manager (pnpm, npm, yarn, or bun)

## Use it

```bash
# new standalone frontend project
uvx copier copy --trust gh:JusticeO21/steerable my-project
```

The generated project is always frontend-only and its application source is
`src/`. The Vite package and configuration files are at the repository root.

```bash
uvx copier copy --trust gh:JusticeO21/steerable shop-web
```

### First run

```bash
cd shop-web
git init                # husky needs a work tree
pnpm install
chmod +x .husky/pre-commit && git config core.hooksPath .husky   # the husky hook
pnpm dev                # http://localhost:5173
```

The Husky hook formats and lints staged frontend files on every commit.

The `scripts` block in `package.json` lists the available commands:

```bash
pnpm run check         # prettier, eslint, FSD, tsc, vitest
pnpm test              # vitest only
```

### What lands in the repository

```
shop/
  AGENTS.md                  rules every agent reads first, plus "START HERE"
  CLAUDE.md, Gemini.md, .github/copilot-instructions.md
  .header.json               commands, paths, and sources, for agents
  docs/
    architecture/            overview, path-rules table, frontend, security
    architecture/decisions/  ADR-000 template + drift check
    product/business-rules.md   BR-<AREA>-<NN>, cited by tests
    engineering/             testing.md, code-review.md
  index.html, vite.config.ts, vitest.config.ts, package.json
  src/
    app/ pages/home/ shared/ui/
  .github/workflows/verify.yml
```

An agent opening `shop/` reads `AGENTS.md`, which points it at
`docs/architecture/path-rules.md` ("which rules apply to this path") and at the
business rules it must not break. Before the first edit it runs the "START
HERE" checks and replaces the `CHECK:confirm` and `TODO: replace` markers —
those are the facts only your project knows, such as where rule IDs come from
and the one invariant the product must never break.

### Wiring it into an existing repository

`copier copy` writes into a directory. For an existing frontend checkout, use `copier apply` with the answers file,
or copy into the existing tree:

```bash
uvx copier copy --trust gh:JusticeO21/steerable .
```

Conflicting files are reported and left untouched unless you pass
`--overwrite`; review each report rather than accepting all of them.

## Update an existing repository

Templates evolve. Re-render to pull fixes without losing local work:

```bash
uvx copier update --trust
```

Copier three-way-merges the template diff against your changes and records the
answers in `.steerable/answers.yml`, so commit that file. The frontend generator
lives in the template; it reruns on update and preserves existing application
code while refreshing template-owned configs.

### Upgrading from v1

v1 shipped the frontend as static files. v2 generates it with `create-vite`
(`template/src/frontend/setup.py`). `copier update` refuses to run on a v1 repository:
the old task list would copy the static tree back in. To move a v1 project:

1. Keep your frontend app code somewhere safe.
2. Run `git rm -r src/frontend` (or move the directory aside), and delete the
   frontend lines from `package.json` scripts.
3. Set `_commit` in `.steerable/answers.yml` to a v2 tag, then run
   `uvx copier update --trust`. The frontend is scaffolded fresh, and FSD
   configs come from v2.
4. Move your slices under `src/`, run
   `pnpm run lint:fsd`, and fix what the check reports.

## Maintain it

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add a question, a document, or
a check, and the naming trap that silently drops generated files.

```bash
python check-template.py
```

renders the standalone frontend project with copier and fails on unrendered
Jinja, broken doc links, a collapsed CI gate list, and server-side artifacts
in the generated output.

## License

[MIT](LICENSE)
