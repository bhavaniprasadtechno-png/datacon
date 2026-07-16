# CLAUDE.md

## Rules

- Do not commit anything (no `git commit`, `git push`, etc.) unless explicitly asked to in that turn.
- **Strictly invoke the relevant superpowers skill for its listed trigger below — every time, no exceptions.** Don't skip brainstorming before creative work, systematic-debugging before a fix, etc. because the task "seems simple."
- **Strictly use codebase-memory's knowledge-graph tools (`search_graph`, `trace_path`, `get_code_snippet`, `query_graph`) for code exploration before falling back to Grep/Glob.** The graph goes stale relative to uncommitted work — re-index before relying on it:
  - `index_repository(repo_path=<repo>, mode="fast")` at the start of a work session, or any time you suspect the graph predates recent changes (fast mode is cheap enough to run often; use `moderate`/`full` for deeper occasional passes).
  - `detect_changes(project, base_branch="main")` to see which symbols a diff affects using the existing graph — this does not rebuild the graph itself.
  - If `search_graph`/`trace_path` can't resolve a name that should exist, that's a signal the index is stale — re-index rather than concluding the symbol is missing.
- **Strictly use context7 to fetch current library/framework/API docs before answering from training data** — for any question or implementation touching a library's API surface (React, Vite, NestJS, Prisma, FastAPI, DuckDB, litellm, Gemini/other LLM provider APIs, etc.). Training data goes stale (model deprecations, renamed APIs, changed defaults); context7 doesn't.

## Skills to use during development

- **superpowers:brainstorming** — before any creative/feature work: new features, components, behavior changes.
- **superpowers:writing-plans** — turn a spec/requirement into a multi-step plan before touching code.
- **superpowers:executing-plans** / **superpowers:subagent-driven-development** — execute an existing plan, with or without subagents.
- **superpowers:test-driven-development** — before writing implementation code for a feature or bugfix.
- **superpowers:systematic-debugging** — for any bug, test failure, or unexpected behavior, before proposing a fix.
- **superpowers:using-git-worktrees** — when feature work needs isolation from the current workspace.
- **superpowers:requesting-code-review** / **superpowers:receiving-code-review** — around completing or reviewing significant changes.
- **superpowers:verification-before-completion** — before claiming work is complete, fixed, or passing.
- **superpowers:finishing-a-development-branch** — once implementation is done and tests pass, to decide merge/PR/cleanup.
- **feature-dev:feature-dev** — guided feature development with codebase/architecture focus.
- **frontend-design:frontend-design** — for `web/` UI work needing intentional visual/design decisions.
- **dataviz** — for any chart/graph/dashboard work (Insights, Forecasts).
- **codebase-memory** — code exploration via the knowledge graph (search_graph, trace_path, get_code_snippet, etc.) before falling back to plain Grep/Glob. See the re-indexing rule above.
- **verify** — exercise a change end-to-end before considering it done.
- **code-review** / **simplify** — reviewing diffs for correctness, reuse, and simplification.
- **security-review** — before shipping changes touching auth, RBAC, or connector secrets.
- **run** — to launch/start the app or a workspace to confirm a change works live.
- **context7** — fetch up-to-date library/framework docs (React, Vite, NestJS, Prisma, FastAPI, etc.) instead of relying on training data. See the strict-use rule above.
