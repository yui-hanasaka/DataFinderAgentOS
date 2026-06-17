# Database Hot-Switch Design

**Date**: 2026-06-18
**Status**: Design approved
**Scope**: 运行时热切换 SQLite ↔ MySQL，保存即生效，自动建表 + 快照数据迁移

---

## 1. Requirements Summary

| Dimension | Decision |
|-----------|----------|
| Activation | Hot-switch — takes effect immediately upon save, no restart |
| Schema | Auto-migration — DDL translated to target dialect on the fly |
| Data | Snapshot migration — one-time bulk copy during switch |
| During switch | Brief lock — block new requests, complete in-flight ones, migrate, unlock |
| Failure handling | Preflight check — test connection + build tables before committing |
| Reverse switch | Symmetric — MySQL → SQLite same flow as SQLite → MySQL |

## 2. Architecture Overview

```
┌─────────────────────────────────────────────┐
│  handlers / repos (existing code, ZERO changes)│
│       ↓ get_connection()                     │
├─────────────────────────────────────────────┤
│  Connection Factory  (modify db.py)          │
│  ├─ read sys_settings.db_type                │
│  ├─ sqlite → sqlite3.connect(DB_PATH)        │
│  └─ mysql  → pymysql.connect(params)         │
│       ↓                                      │
│  DatabaseConnection Wrapper  (new in db.py)  │
│  ├─ unified DictCursor → row["col"] access   │
│  ├─ transparent ? ↔ %s placeholder swap      │
│  └─ unified context manager behavior         │
├─────────────────────────────────────────────┤
│  DDL Translator  (new: db_ddl.py)            │
│  ├─ init_db() dual-path → SQLite / MySQL     │
│  └─ ~10 syntax rewrite rules                 │
├─────────────────────────────────────────────┤
│  DatabaseSwitcher  (new: db_switcher.py)     │
│  ├─ preflight()  → test + build              │
│  ├─ lock()       → block incoming requests   │
│  ├─ migrate()    → snapshot-copy all tables   │
│  └─ switch()     → update state + unlock      │
└─────────────────────────────────────────────┘
```

**Files touched:**
- `app/models/db.py` — modify `get_connection()` and `init_db()`; add `DatabaseConnection` wrapper
- `app/models/db_ddl.py` — new file, DDL dialect translation
- `app/models/db_switcher.py` — new file, switch orchestration
- `app/controllers/settings.py` — modify, call switcher on save
- `test/test_db.py` — extend existing tests
- `test/test_db_switcher.py` — new test file

**Files NOT touched:** All Repos, Handlers, templates, JS — zero changes needed.

## 3. Connection Wrapper (`DatabaseConnection`)

Unifies `sqlite3.Connection` and `pymysql.connections.Connection` behind a thin wrapper.

### Behavior matrix

| Concern | SQLite | MySQL (pymysql) | Unified via |
|---------|--------|-----------------|-------------|
| Placeholder | `?` | `%s` | Wrapper swap (MySQL path only) |
| Row access | `sqlite3.Row["col"]` | `DictCursor["col"]` | Natural compatibility |
| Context manager | `__enter__`/`__exit__` commit/rollback | Same | Natural compatibility |
| `executemany` | Native | Native (swap `?`→`%s`) | Wrapper |
| `executescript` | Native | **None** — split & loop | SQLite path only |
| `lastrowid` | Native | Native | Natural compatibility |
| `PRAGMA` | Native | **None** — no-op or `SHOW COLUMNS` equivalent | SQLite path only |

### Interface

```python
class DatabaseConnection:
    conn: sqlite3.Connection | pymysql.connections.Connection

    def execute(self, sql: str, params=None) -> Cursor: ...
    def executemany(self, sql: str, seq) -> Cursor: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *args) -> None: ...   # commit on success, rollback on exception
```

### Placeholder swap

- MySQL path: `?` → `%s` via `str.replace("?", "%s")` before sending to pymysql
- Guard: project SQL never contains `?` inside string literals (verified by review)

### `get_connection()` logic

```python
_active_db_type: str = "sqlite"  # or "mysql", loaded at startup and updated on switch
_switch_lock = threading.Lock()

def get_connection() -> DatabaseConnection:
    _switch_lock.acquire()
    _switch_lock.release()  # immediate release for normal reads
    # brief hold during switch — see §5

    if _active_db_type == "mysql":
        return _mysql_connect()
    return _sqlite_connect()
```

## 4. DDL Translation Rules

SQLite `CREATE TABLE` statements are translated to MySQL at runtime. No dual-DDL maintained.

### Complete translation table

| # | SQLite | MySQL | Occurrences | Risk |
|---|--------|-------|-------------|------|
| 1 | `AUTOINCREMENT` | `AUTO_INCREMENT` | 17 tables | Low |
| 2 | `INTEGER PRIMARY KEY AUTOINCREMENT` | `INT PRIMARY KEY AUTO_INCREMENT` | 17 tables | Low |
| 3 | `TEXT NOT NULL DEFAULT (datetime('now'))` | See §4.1 | ~30 columns | **High** |
| 4 | `REAL` | `DOUBLE` | 1 column | Low |
| 5 | `INSERT OR IGNORE` | `INSERT IGNORE` | ~6 places | Low |
| 6 | `ON CONFLICT(key) DO UPDATE` | `ON DUPLICATE KEY UPDATE` | 1 place | Low |
| 7 | `PRAGMA foreign_keys = ON` | Skip (InnoDB enables FKs by default) | 1 place | Low |
| 8 | `PRAGMA table_info(x)` | `SHOW COLUMNS FROM x` | migration check | Low |
| 9 | `conn.executescript(...)` | Split into individual `execute()` calls | 1 place | Low |
| 10 | `CREATE UNIQUE INDEX IF NOT EXISTS` | `CREATE UNIQUE INDEX ...` wrapped in try/except | 1 place | Medium |

### 4.1 The TEXT DEFAULT Problem (Risk #3)

MySQL does NOT allow `TEXT` columns with `DEFAULT (expression)`. Strategy:

- **`created_at` / `updated_at` columns**: Change type to `DATETIME` + MySQL `DEFAULT CURRENT_TIMESTAMP`. SQLite path keeps `datetime('now')` which also produces ISO-8601 datetime strings — consistent behavior.
- **All other `TEXT ... DEFAULT (datetime('now'))` instances**: Scanned — every case is a `created_at` or `updated_at` column. No action needed beyond the above.
- **`TEXT NOT NULL DEFAULT ''`**: No datetime expression → no issue. Comma-separated defaults like `'[]'`, `'{}'` work fine on both engines.

### Translation function

```python
# db_ddl.py
def to_mysql(sql: str) -> str:
    """Translate a SQLite DDL statement to MySQL-compatible syntax."""
    sql = sql.replace("AUTOINCREMENT", "AUTO_INCREMENT")
    sql = sql.replace("INTEGER PRIMARY KEY", "INT PRIMARY KEY")
    # TEXT DEFAULT (datetime('now')) → DATETIME DEFAULT CURRENT_TIMESTAMP
    sql = re.sub(
        r"TEXT NOT NULL DEFAULT \(datetime\('now'\)\)",
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        sql,
    )
    sql = sql.replace("REAL", "DOUBLE")
    return sql

def to_mysql_dml(sql: str) -> str:
    """Translate INSERT/UPDATE for MySQL."""
    sql = sql.replace("INSERT OR IGNORE", "INSERT IGNORE")
    # ON CONFLICT(key) DO UPDATE SET col=excluded.col
    #   → ON DUPLICATE KEY UPDATE col=VALUES(col)
    # Only 1 call site (sys_settings upsert); handled inline rather than regex
    return sql
```

## 5. Switch Orchestration (`DatabaseSwitcher`)

### Flow

```
Admin clicks "Save Settings"
        │
        ▼
┌─────────────────┐
│ 1. preflight()  │  Test new DB connection → create tables → verify read/write
│    FAIL → abort  │
└───────┬─────────┘
        │ PASS
        ▼
┌─────────────────┐
│ 2. lock()       │  Acquire _switch_lock, held for duration
│                  │  New get_connection() calls block (5s timeout → 503)
│                  │  In-flight requests complete normally
└───────┬─────────┘
        ▼
┌─────────────────┐
│ 3. migrate()    │  For each table (topological order):
│                  │    SELECT * FROM old_db
│                  │    TRUNCATE target table in new_db
│                  │    INSERT rows into new_db
│                  │  17 tables → <2s for typical data volumes
└───────┬─────────┘
        ▼
┌─────────────────┐
│ 4. switch()     │  Update sys_settings (persist db_type)
│                  │  Update _active_db_type in memory
│                  │  Release _switch_lock
└─────────────────┘
        │
        ▼
  Return "Settings saved" + new requests use new DB
```

### Lock behavior

| Phase | Lock state | Request behavior |
|-------|-----------|-----------------|
| Normal operation | Released | Instant acquire + release |
| During switch | Held by switcher | Block up to 5s, then 503 |
| After switch | Released | New DB connection |

### Migration table order

Topological sort by foreign-key dependencies:

1. `users`, `admin_roles`, `ai_models`, `skills`, `sys_settings`, `watchtower_sources`, `deep_tasks`, `data_warehouse`, `screen_configs`, `digital_twin_scenes` (no FK deps)
2. `admin_users`, `admin_menus`, `chat_sessions`, `digital_employees`, `api_keys`, `screen_widgets`, `digital_twin_models`, `watchtower_items` (FK to layer 1)
3. `admin_role_menus`, `chat_messages`, `deep_contents`, `ai_model_usage`, `ask_history`, `agent_decisions` (FK to layer 1 or 2)

### Failure handling

- `preflight()` failure → never acquires lock → old DB untouched → error returned to admin
- `migrate()` failure → release lock without updating `_active_db_type` → old DB still active → error returned
- If `switch()` itself fails (unlikely — only an in-memory assignment), rollback `_active_db_type` and release lock

### Reverse switch (MySQL → SQLite)

Identical flow. `preflight()` verifies SQLite file is writable (always true on local disk). `migrate()` copies data from MySQL back to SQLite.

## 6. Startup Behavior

At startup, `init_db()`:

1. Connect to SQLite (always — it's the bootstrap DB, always available)
2. Run `CREATE TABLE IF NOT EXISTS` for all tables
3. Seed default data (roles, users, skills, etc.)
4. Read `sys_settings.db_type`:
   - If `"sqlite"` → `_active_db_type = "sqlite"` — done
   - If `"mysql"` → attempt MySQL connection:
     - **Success** → run init DDL on MySQL (`CREATE TABLE IF NOT EXISTS`), seed if empty → `_active_db_type = "mysql"` — but do NOT migrate data (migration only happens on explicit switch)
     - **Fail** → log warning → `_active_db_type = "sqlite"` — fallback (don't crash the server)

## 7. Testing Strategy

### Test cases

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Existing SQLite tests pass unchanged | 6/6 green |
| 2 | `DatabaseConnection` wrapper — SQLite path | Same behavior as raw `sqlite3.Connection` |
| 3 | `DatabaseConnection` wrapper — MySQL path (if MySQL available) | Same behavior, row["col"] access works |
| 4 | DDL translation — all 17 CREATE TABLEs produce valid MySQL | MySQL accepts without syntax error |
| 5 | Placeholder swap — `?` → `%s` for INSERT/SELECT | Correct results both paths |
| 6 | Preflight rejects bad MySQL params | Exception raised, lock never held |
| 7 | Preflight accepts good params | Tables created in MySQL |
| 8 | Full switch: SQLite → MySQL (temp MySQL) | Data migrated, _active_db_type updated |
| 9 | Full switch: MySQL → SQLite | Data migrated back, _active_db_type reverted |
| 10 | Lock blocks concurrent requests | Thread blocks, then proceeds after unlock |
| 11 | Migration with empty tables | No errors, 0 rows copied per table |
| 12 | Migration with data | Row counts match after migration |
| 13 | Switch failure mid-migration | Old DB still active, lock released |
| 14 | Startup with `db_type=mysql` but unreachable MySQL | Falls back to SQLite, server starts |

### Test infrastructure

- `test_db.py` tests run against SQLite with `tmp_db` fixture — unchanged
- `test_db_switcher.py` tests need a temporary SQLite + a temporary MySQL:
  - SQLite: `tmp_db` fixture (already exists)
  - MySQL: use `pymysql` against a separate test database; skip tests if `MYSQL_TEST_HOST` env var not set
  - Most tests can verify SQLite↔SQLite switch logic without real MySQL

## 8. Explicit Non-Goals

- No PostgreSQL / other database support (architecture supports future addition)
- No large-dataset performance optimization (project is single-user / small-team scale)
- No multi-process lock coordination (Tornado is single-process)
- No online schema migration (table structure is stable)
- No MySQL → SQLite data migration on startup (switches only happen via explicit admin action)
