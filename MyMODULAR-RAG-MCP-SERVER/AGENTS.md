# Modular RAG MCP Server development contract

## Source of truth

- Treat `DEV_SPEC_selfrag.md` as the authoritative product specification, architecture, task schedule, and acceptance contract.
- Treat `DEV_SPEC.md` only as the historical baseline. It must not drive architecture decisions, implementation scope, task selection, progress updates, or acceptance unless the user explicitly requests work against the legacy baseline.
- Read the target task in section 6 plus the relevant architecture, technology, and testing sections before editing code.
- If existing code and the specification disagree, report the mismatch and follow the specification unless the user explicitly changes scope.
- Keep `README.md`, configuration examples, and public interfaces consistent with implemented behavior.

## Vibe-coding workflow

- For requests to build, continue, auto-code, or implement the next item, use the repository `$auto-coder` skill.
- Work on one explicit `DEV_SPEC_selfrag.md` task ID at a time unless the user clearly requests a bounded sequence.
- Select the first `[~]` task before the first `[ ]` task; honor an explicitly requested task ID.
- Verify predecessor artifacts before implementation. Stop only when the target cannot be completed safely; otherwise state the assumption and continue.
- Before editing, inspect `git status` and preserve unrelated user changes.
- Do not broaden a task into future-roadmap work from section 7 without explicit user direction.

## Architecture rules

- Preserve the layered design: `mcp_server` -> `core` -> pipelines and `libs`; observability must not become a hidden business-logic dependency.
- Keep providers and strategies pluggable behind base contracts and factories.
- Drive provider, model, retrieval, reranking, storage, evaluation, and dashboard behavior from `config/settings.yaml`; do not hardcode environment-specific values.
- Keep core data contracts centralized in `src/core/types.py` when the specification assigns them there.
- Prefer dependency injection and small composable units. Avoid provider checks scattered through orchestration code.
- Maintain deterministic fallbacks for optional LLM, vision, reranker, evaluator, and external-service failures where the specification requires graceful degradation.

## Python and environment

- Target Python 3.10 or newer unless `pyproject.toml` later narrows the supported range.
- On Windows, prefer `.\.venv\Scripts\python.exe`; on macOS/Linux, prefer `.venv/bin/python`.
- Do not assume the virtual environment or `pyproject.toml` exists on this clean-start branch. Create or install them only when the active task or user request requires it.
- Never print, commit, invent, or overwrite real API keys. Use environment variables, placeholders, mocks, and ignored local credential files.
- Do not make live provider calls unless the user supplied the required credentials and the test explicitly needs them.

## Implementation and tests

- Implement the smallest complete change that satisfies the task's listed files, contracts, and acceptance criteria.
- Add or update tests alongside production code. Put isolated tests in `tests/unit`, cross-component tests in `tests/integration`, and full workflows in `tests/e2e`.
- Mock network APIs, hosted models, clocks, and nondeterministic dependencies in unit tests.
- Run the narrowest relevant test first, then the broader affected suite. Run lint or type checks once their configuration exists and the changed scope warrants them.
- A test is not passed unless its command completed successfully in the current session. Report skipped tests and missing prerequisites explicitly.
- For formal QA-plan execution, use `$qa-tester`; preserve its strict serial evidence and progress-recording rules.

## Progress and completion

- Do not mark a task `[x]` until its acceptance criteria are met and required tests pass.
- When completing a task, update its row in `DEV_SPEC_selfrag.md` with status, date, and concise evidence, then update the aggregate progress table accurately.
- Keep auto-coder references synchronized from `DEV_SPEC_selfrag.md` only. Before running `.agents/skills/auto-coder/scripts/sync_spec.py`, verify that it is configured to read `DEV_SPEC_selfrag.md`; never allow the legacy `DEV_SPEC.md` to overwrite the active references.
- Summarize changed files, verification commands, results, skipped checks, and remaining risks at handoff.
- Never create a Git commit, push, or rewrite history unless the user explicitly requests it.

## Review priorities

- Protect configuration compatibility, stable IDs, idempotent ingestion, metadata and citation integrity, deterministic ranking, protocol correctness, and cleanup across all persistent stores.
- Treat silent fallbacks, stale indexes, cross-collection leakage, raw exceptions over MCP stdio, and secrets in logs as high-priority defects.
