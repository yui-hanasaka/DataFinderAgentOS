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

**biome note:** `app/static/js/base.js` may show CRLF line-ending errors — run `npx @biomejs/biome check --write app/static/js/base.js` to fix (pre-existing; not related to code changes).

## Architecture

**Entry point:** `app.py` — registers all routes and starts the Tornado server. `init_db()` runs on startup to create/migrate all 26 SQLite tables (MySQL DDL mirrors exist in `db.py::_init_mysql_tables`). `KeyboardInterrupt` is caught to suppress traceback on Ctrl+C.

**Two independent auth systems:**
- Frontend users: `username` secure cookie, verified via `app/models/user.py::UserRepository`
- Admin users: `admin_username` secure cookie, verified via `app/models/admin.py::AdminRepository`

**Request flow:** Route → Handler (inherits `AdminBaseHandler` or `BaseHandler`) → Repository (`app/models/`) → SQLite via `get_connection()` in `app/models/db.py`. Dual-path connection factory exists (`DatabaseConnection`, `DatabaseSwitcher`) with MySQL startup fallback — SQLite is the active default.

### Agent system (`app/agents/`)

**ReAct loop** (`agent_loop.py`): up to 8 turns. Each turn streams text via SSE, then model returns tool_calls. Before executing, `tool_reviewer.py` calls an independent AI review (fail-closed: deny if review unavailable). Reviewed tools execute via `tool_executor.py`. `env_info` and `watchtower_search` skip review.

**Tools** (6 registered in `tool_registry.py`): `web_search`, `code_execute`, `watchtower_search`, `warehouse_query`, `deep_collect`, `env_info`. `web_search` uses Bing HTML scraping as primary (works in China), DuckDuckGo Instant Answer as fallback — both in `tool_executor.py` and `skill_dispatcher.py`.

**code_sandbox.py**: AST-static-analysis whitelist approach. Blacklists 13 modules (`subprocess`, `os`, `socket`, …). Runs in subprocess with 15s timeout, stdout capped at 8KB.

### SSE streaming chat

`ChatSendHandler.post()` writes `text/event-stream` manually with `self.write("data: ...\n\n")` + `await self.flush()`. Event types: `text`, `tool_call`, `tool_review`, `tool_result`, `music_html`. Errors caught with `log_error` (→loguru, one-line output, NO full traceback).

**Frontend** (`chat.html`): SSE reader creates one assistant bubble per agent turn. Tool cards are separate DOM elements between bubbles (`_newTurn` flag set on `tool_result`). AbortController-based stop button. `music_html` events bypass markdown rendering and set innerHTML directly.

### Skill dispatcher (`skill_dispatcher.py`)

Parses message prefixes, returns `DispatchResult = dict[str, Any]` with `type`, `skill_code`, `processed_content`, `skill_meta`:

| Prefix | Skill | Backend |
|---|---|---|
| `@weather` / `@天气` | Weather | uapis.cn free API (default), OpenWeatherMap (if key configured) |
| `@music` / `@音乐` | Music search | `music.chinokou.cn` Netease API (default, no config needed), external keys from `api_keys` table |
| `@西师妹` | Campus AI | Routes to AI with system_override persona |
| `\search` | Web search | Bing HTML scrape (primary), DuckDuckGo (fallback) |

### Music search (`MusicSearchHandler`)

Parallel query flow: ① `music.chinokou.cn/cloudsearch` (built-in, no key required) ② external configured API keys ③ iTunes fallback. Frontend: search card renders clickable song list with ▶ buttons → clicking creates new chat bubble with Netease official iframe player (`music.163.com/outchain/player`).

### Watchtower (`app/models/watchtower.py`, `watchtower_scraper.py`, `watchtower_collect.py`, `watchtower_agent.py`)

**Scraping:** `WatchtowerScraper` supports 8 source types (baidu_news, bing_web, bing_news, duckduckgo, sogou_web, rss, api, generic). When requests+BS4 returns empty (anti-bot), auto-falls-back to crawl4ai headless browser. Collection runs in parallel via `asyncio.gather` with 25s per-source timeout.

**Deep collection:** `run_deep_collect_task()` (standalone coroutine in `deep.py`) — crawls item URLs with crawl4ai → requests+BS4 fallback → AI summarization. Skips `baidu.com/link?url=` intermediary redirect links. Shared crawl4ai browser across batch items.

**AI scheduling:** `WatchtowerAgent` runs every 30min via Tornado `PeriodicCallback`. AI decides `scrape_source` / `trigger_deep_collect` / `log_observation` actions.

### Database migrations

`_run_migrations()` checks `schema_migrations` table, applies versioned SQL via `_migrate()`. Supports idempotent `ALTER TABLE ADD COLUMN` (checks `PRAGMA table_info` first). 10 registered migration versions (v1–v4 with subtypes).

### Logging

`setup_logging()` in `errors.py` configures loguru: console sink (colored, DEBUG level) + file sink (`database/datafinder.log`, INFO, 10MB rotation). Third-party loggers silenced to WARNING: `crawl4ai`, `playwright`, `httpx`, `httpcore`, `urllib3`.

`log_error(context, exc)` logs one line only — `logger.error("{} — {}", context, exc)` — no traceback.

## Key model files

- `db.py` — `get_connection()` returns `sqlite3.Connection` with `row_factory = sqlite3.Row`; `init_db()` creates 26 tables and seeds defaults
- `model_client.py` — `httpx.AsyncClient` singleton for OpenAI-compatible API; `chat_complete()` (with 2 retries on 429/5xx), `iter_sse_chunks()` for SSE parsing
- `model_engine.py` — `ModelRepository` CRUD for `ai_models` table
- `deep.py` — `DeepRepository` + `run_deep_collect_task()` + `_repair_truncated_json()` + `_extract_json_from_model_output()` (shared JSON repair utilities)
- `employee.py` — `EmployeeRepository`; `list_all_active()` JOINs `ai_models` to include `model_name`
- `secrets_store.py` — `decrypt()` / `encrypt()` for `api_keys.api_key` field

## Templates

Tornado's own template engine (not Jinja2). `{% block body %}...{% end %}`, `{% for x in items %}...{% end %}`. Admin templates inherit `admin/base.html`; web templates inherit `web/base.html` (referenced as `"web/base.html"` from controllers in `app/controllers/web/` — BUT the `chat.py` controllers reference `"web/chat.html"` directly).

**Historical messages + music cards:** `{% raw m["content"] %}` for messages where `m["skill_meta"]` contains `"music"` — bypasses Tornado's auto-escaping so HTML cards render.

## Type annotations

Python 3.12+ style only: `X | None`, `list[X]`, `dict[K, V]`, `tuple[X, Y]`. No `from __future__ import annotations`, no `Optional`/`List`/`Dict` from `typing`.

**sqlite3.Row access:** Always use bracket notation `row["column"]` — dot notation raises `AttributeError`. When summing Row values pass through `int()`: `sum(int(r["count"]) for r in rows)`.

## Adding features

- **New route:** add Handler in `app/controllers/`, inherit `AdminBaseHandler` (admin) or `ChatBaseHandler` (web, defined in `chat.py`), register in `app.py`
- **New table:** add `CREATE TABLE IF NOT EXISTS` in `app/models/db.py::_init_business_tables()` AND in `_init_mysql_tables()`, call from `init_db()`
- **New test:** use `tmp_db` fixture (test_db.py) or `db_with_user` fixture (test_chat_repo.py) — they monkey-patch `db_module.DB_PATH` to an isolated temp file per test
- **New migration:** register in `_run_migrations()` with a unique version key; for `ALTER TABLE ADD COLUMN`, the `_migrate()` function handles idempotency via `PRAGMA table_info`
