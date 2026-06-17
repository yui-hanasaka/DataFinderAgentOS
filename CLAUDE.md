# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run python app.py                       # start server on :10086 (autoreload enabled)
uv run pytest                              # all tests
uv run pytest test/test_db.py              # single file
uv run pyright                             # type check (standard, Python 3.12+)
uv run ruff check .                        # lint
uv run ruff format .                       # format
npx @biomejs/biome check                  # JS/CSS lint + format
npx eslint app/static/js/ app/templates/ --ext .html,.js  # JS lint (incl. inline scripts)
uv run python scripts/check_templates.py   # template syntax checker
```

## Quality Gate (mandatory after every task)

After completing any code change, run ALL checks in order and ensure 100% pass:

```
1. uv run ruff check .                        # 0 errors
2. uv run ruff format .                       # no changes left
3. uv run pyright                             # 0 errors, 0 warnings, 0 informations
4. npx @biomejs/biome check                   # 0 errors, 0 warnings
5. npx eslint app/static/js/ app/templates/ --ext .html,.js  # 0 real errors (see note)
6. uv run python scripts/check_templates.py   # 0 template issues
```

**Strict rules:**
- Zero `#noqa` comments allowed anywhere — fix the root cause instead.
- Zero `# type: ignore` comments allowed anywhere — fix the type issue instead.
- Zero `/* eslint-disable */`, `// biome-ignore`, `<!-- eslint-disable -->` comments allowed anywhere.
- NEVER use Bash (`sed`/`cat`/`grep` etc.) or PowerShell to edit file content. Use the dedicated Read / Write / Edit tools instead.
- If ruff format produces changes, re-run ruff check afterwards.
- pyright must report `0 errors, 0 warnings, 0 informations` — no suppressed diagnostics of any severity.
- Run all checks sequentially and report the output verbatim. Do not skip any check.

**ESLint note:** `Parsing error: Unexpected token {` on lines containing `{{ }}` in `<script>` blocks is a known false positive — ESLint cannot parse Tornado template syntax inside JavaScript. These 2 files (screen.html, ask.html) are verified by the template checker (step 6) instead. All other ESLint errors must be zero.

## Architecture

**Entry point:** `app.py` — registers all routes and starts the Tornado server. `init_db()` runs on startup to create/migrate all SQLite tables.

**Two independent auth systems:**
- Frontend users: `username` secure cookie, verified via `app/models/user.py::UserRepository`
- Admin users: `admin_username` secure cookie, verified via `app/models/admin.py::AdminRepository`

**Request flow:** Route → Handler (inherits `AdminBaseHandler` or `BaseHandler`) → Repository (`app/models/`) → SQLite via `get_connection()` in `app/models/db.py`

**Key model files:**
- `db.py` — `get_connection()` returns `sqlite3.Connection` with `row_factory = sqlite3.Row`; `init_db()` creates all 17 tables and seeds default admin/roles/skills
- `model_client.py` — thin wrapper around `httpx.AsyncClient` for OpenAI-compatible API calls; `chat_complete()` returns a raw `HTTPResponse`, `iter_sse_chunks()` yields parsed SSE dicts
- `skill_dispatcher.py` — parses `@weather`, `@music`, `@西师妹`, `\search` prefixes; returns `DispatchResult = dict[str, Any]` with keys `type`, `skill_code`, `processed_content`, `skill_meta`

**Streaming chat:** `ChatSendHandler.post()` and `AdminModelChatHandler.post()` both write `text/event-stream` responses manually with `self.write("data: ...\n\n")` + `await self.flush()`. XSRF is disabled on these endpoints via `check_xsrf_cookie = pass`.

**Templates:** Tornado's own template engine (not Jinja2). Use `{% block body %}...{% end %}`, `{% for x in items %}...{% end %}`. Admin templates inherit `admin/base.html`; web templates inherit `base.html` (located at `app/templates/base.html`, referenced as `"base.html"` not `"web/base.html"`).

**sqlite3.Row access:** Always use bracket notation `row["column"]` — dot notation raises `AttributeError`. When summing Row values pass through `int()`: `sum(int(r["count"]) for r in rows)`.

## Adding features

- **New route:** add Handler in `app/controllers/`, inherit `AdminBaseHandler` (admin) or `ChatBaseHandler`/`AskBaseHandler` (web, defined inline in their controller files), register in `app.py`
- **New table:** add `CREATE TABLE IF NOT EXISTS` in `app/models/db.py::_init_business_tables()`, call from `init_db()`
- **New test:** use `tmp_db` fixture (test_db.py) or `db_with_user` fixture (test_chat_repo.py) — they monkey-patch `db_module.DB_PATH` to an isolated temp file per test

## Type annotations

Python 3.12+ style only: `X | None`, `list[X]`, `dict[K, V]`, `tuple[X, Y]`. No `from __future__ import annotations`, no `Optional`/`List`/`Dict` from `typing`.
