# Contributing

This repository is a copier template. A change is correct when the standalone
frontend renders cleanly and the generated repository passes its own gates.
The gates have to run in the generated repo, not in the template, because
template files are `.jinja` text until copier renders them.

## Run the checks

```bash
uv tool install copier      # once
python check-template.py
```

It renders the frontend project into the system temp directory and fails on:

- unrendered Jinja in `.md`, `.mjs`, `.py`, `.toml`, `.yaml`, `.json`;
- a Markdown link whose target does not exist in that scope;
- a CI gate list in `AGENTS.md` that collapsed into one line;
- server-side files in the generated frontend repository;
- a path named in `.header.json` toolchains that the scope did not generate;
- a missing frontend `package.json` script or toolchain file.

GitHub Actions runs the same script on Linux and Windows, then runs the
generated project's real `check` command. A template change that only passes on
the author's machine will fail there.

## Layout

```
copier.yml                  questions and their defaults
check-template.py           the harness above
template/                   copied verbatim, with .jinja rendered
  AGENTS.md.jinja           the entrypoint for every agent
  .header.json.jinja        machine-readable facts about the generated repo
  {% if frontend %}...{% endif %}.jinja  conditional files
  docs/                     architecture, product, engineering docs
  src/frontend/setup.py     template-only generator: create-vite + FSD adapter
  .github/, .husky/
```

## The frontend is generated, not copied

`template/src/frontend/setup.py` is run directly from the template source; it
is not copied into generated apps. It puts package files at the repository root
and FSD layers under `src/`, runs `create-vite` (`react-ts --eslint`), adapts
the entry point, removes the demo screen, writes the FSD slices and configs,
and installs the extra packages. On `copier update`, it preserves app code and
refreshes template-owned files.

- The task is a dict: `command` runs `{{ _copier_python }}` (the interpreter
  that has copier) on `{{ _copier_conf.src_path }}/template/src/frontend/setup.py`, and
  `working_directory` is the destination.
- Answers reach it through `.header.json` (`answers`), not through Jinja: the
  task list is read before questions render, and a task cannot see them.
  The script runs from the repository root and reads `frontend_root` and
  `frontend_source_root` from `.header.json`.
- `check-template.py` renders with `STEERABLE_NO_INSTALL=1`: the same files
  are written, without create-vite or a network round trip. CI runs it once
  with installs.
- Configs live in the template script's `CONFIGS` table and are substituted with
  `.replace`, not f-strings: TS templates nest `{ }`. `tsconfig.e2e.json` is
  the one file written to the repository root (`playwright.config.ts` and
  `e2e/` live there); every package it imports is in the app's `node_modules`.
## The one naming trap

`{% if %}` in a **file name** is a feature: copier renders the name and drops
the file when it renders empty.

`{% if %}` in a **directory name** is a bug. Copier does not recurse into a
directory whose rendered name is empty, so every file under it vanishes and the
render still reports success. The harness (`check_layout`) rejects conditional
directories; keep conditional files inside normal directories.

When you add or rename a conditional file, update `PROVEN` in
`check-template.py` if it is an architecture doc or verify script, so a silent
disappearance fails the build.

## Adding a question

1. Add it to `copier.yml` with a `default`. `--defaults` is how CI and the
   harness render, so a question without a default breaks generation.
2. Give it a `when:` if it only applies to frontend generation (`{{ frontend }}`).
3. Use it in a doc or a command, and reference the value rather than repeating
   it. The same fact stated twice drifts.
4. If a default is derived from the scope, derive it in Jinja instead of asking
   an agent to fill it in later.

This repository only generates a frontend. `copier.yml` validates the fixed
frontend scope and root source paths to prevent alternate layouts.

## Adding a document

- Every project gets the file; frontend-specific sections use
  `{%- if frontend %}` inside it.
- Link it from `AGENTS.md` or a sibling doc by relative path; the harness fails
  on a broken link.
- A fact the project must supply goes in as a `CHECK:confirm` marker or a
  `TODO: replace` placeholder, with the default stated next to it. Step 2 of
  the generated "START HERE" greps for both markers.
- Commands come from `copier.yml` variables (`{{ check_command }}`,
  `{{ dev_command }}`, ...), never typed twice.

## Adding a check to the generated repository

- A check that guards structure (layers, boundaries, doc drift) belongs in
  `docs/architecture/*.verify.mjs` or the frontend `check` script, so it runs
  locally and in generated CI.
- Wire it into the `check` script in `package.json`. Fail by exit code; a check
  that only warns is a comment.
- Run the new check on a repository generated by the harness and confirm it
  fails when the rule is violated, then passes when restored. A check that has
  never failed is not known to work.

## Commit messages

Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`.
