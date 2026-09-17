---
name: auto-coder
description: Implement one verified task at a time from DEV_SPEC_selfrag.md, reusing the read-only traditional RAG baseline when appropriate. Use for spec-driven implementation, baseline migration, "auto code", "auto dev", "自动开发", "自动写代码", or continuing the next Self-RAG task.
---

# Auto Coder

Drive development from `DEV_SPEC_selfrag.md` through a repeatable cycle:

```text
Sync spec -> select one task -> inspect baseline -> implement or migrate -> test -> update progress
```

## Authoritative inputs

- `DEV_SPEC_selfrag.md` is the only source of truth for architecture, scope, task status, acceptance criteria, and progress.
- `DEV_SPEC.md` is historical context only. Never select work from it, update its task status, or sync it into this skill.
- Follow the repository `AGENTS.md` for project-wide development constraints.
- Treat `../MODULAR-RAG-MCP-SERVER` as a read-only traditional RAG baseline, not as a second specification.

## Invocation and scope

- Work on exactly one task per invocation unless the user explicitly requests a bounded sequence.
- An explicit task ID, such as `$auto-coder J2`, takes precedence over automatic selection.
- Otherwise, select the first `[~]` task and then the first `[ ]` task in the synchronized schedule.
- Do not implement later tasks opportunistically. Small prerequisite fixes are allowed only when necessary for the selected task and must be reported.
- Do not create a Git commit by default. Commit only after the user explicitly requests it.

## 1. Sync the specification

Run from the project root, using the project virtual-environment interpreter when it exists and a system Python interpreter otherwise:

```powershell
python .agents/skills/auto-coder/scripts/sync_spec.py
```

Then read `.agents/skills/auto-coder/references/06-schedule.md` and the references relevant to the selected task:

| Reference | Use |
|---|---|
| `01-overview.md` | Product goals and constraints |
| `02-features.md` | Feature behavior |
| `03-tech-stack.md` | Dependencies, configuration, and implementation choices |
| `04-testing.md` | Test strategy and acceptance gates |
| `05-architecture.md` | Modules, data flow, and interface contracts |
| `06-schedule.md` | Task order, status, details, and acceptance criteria |
| `07-future.md` | Roadmap context only; not current scope |

## 2. Inspect before editing

1. Inspect `git status` and preserve unrelated user changes.
2. Extract the selected task's required files, interfaces, dependencies, tests, and acceptance criteria.
3. Verify predecessor artifacts in the target project.
4. Search the target project for an existing implementation before creating new code.
5. When the target lacks a traditional RAG capability, inspect the corresponding implementation and tests in the read-only baseline.

## Baseline migration rules

- Prefer migrating a baseline implementation that already satisfies the required contract over rewriting equivalent traditional RAG code.
- Keep the target architecture and public interfaces compatible with `DEV_SPEC_selfrag.md`; adapt migrated code only where the Self-RAG specification requires it.
- Never modify `../MODULAR-RAG-MCP-SERVER`.
- Never copy the baseline `.git`, `.claude`, virtual environments, caches, generated build artifacts, runtime data, databases, logs, credentials, secrets, or local environment files.
- Preserve target-owned files including `AGENTS.md`, `.agents/`, `DEV_SPEC_selfrag.md`, and the target repository metadata.
- Treat source tests and source progress records only as reuse evidence. After migration, run the relevant tests in the target project; a source-side pass is not target-side acceptance evidence.
- Do not mark a migrated task complete until its current acceptance criteria pass in the target project. Use `[~]` and report missing prerequisites when verification is incomplete.

## 3. Implement or migrate

1. State a concise file plan before editing.
2. Implement the smallest complete change for the selected task.
3. Preserve the layered architecture and provider/factory contracts defined by the specification.
4. Keep environment-specific behavior config-driven; never hardcode credentials, provider model IDs, endpoints, or local paths.
5. Add or migrate tests alongside production code. Mock hosted models and external services in unit tests.
6. Review imports, configuration compatibility, data contracts, fallbacks, and public API behavior before testing.

## 4. Test and repair

1. Run the narrowest relevant tests first.
2. Run the broader affected suite required by the task's acceptance criteria.
3. Apply up to three focused repair rounds when tests fail because of the current change.
4. Stop and report evidence when failure depends on missing credentials, unavailable infrastructure, incompatible external state, or a defect outside the authorized scope.
5. Never claim skipped or unexecuted tests as passing.

## 5. Persist progress

Only after acceptance criteria and required tests pass:

1. Update the selected task in `DEV_SPEC_selfrag.md` from `[ ]` or `[~]` to `[x]`.
2. Record the date and concise target-side verification evidence.
3. Update aggregate progress figures accurately.
4. Re-sync references:

```powershell
python .agents/skills/auto-coder/scripts/sync_spec.py --force
```

At handoff, report changed files, reused baseline files, verification commands and results, skipped checks, remaining risks, and the next eligible task. Leave all changes uncommitted unless the user explicitly authorizes a commit.
