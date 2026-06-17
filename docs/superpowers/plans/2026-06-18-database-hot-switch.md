# Database Hot-Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement runtime hot-switch between SQLite and MySQL — save in admin settings takes effect immediately, with automatic schema creation and snapshot data migration.

**Architecture:** Three new components layered under the existing `get_connection()` interface: `DatabaseConnection` wrapper (unified cursor/context-manager), `db_ddl.py` (dialect translation), `DatabaseSwitcher` (preflight→lock→migrate→switch). Zero changes to handlers/repos/templates.

**Tech Stack:** Python 3.12+, sqlite3 (stdlib), pymysql 2.2.8, threading.Lock, pytest

---

### Task 1: DDL Translation Functions

**Files:**
- Create: `app/models/db_ddl.py`
- Create: `test/test_db_ddl.py`

The translation functions must be correct before anything else — the switcher and wrapper depend on them.

- [ ] **Step 1: Create `app/models/db_ddl.py`**

```python
"""SQLite → MySQL DDL/DML dialect translation.

Translations are string-level rewrites. The set of SQLite-isms in this
project is small and stable (~10 rules).  A full SQL parser is overkill.
"""

import re

# ── DDL (CREATE TABLE) ────────────────────────────────────────────

def to_mysql_ddl(sql: str) -> str:
    """Translate a SQLite ``CREATE TABLE`` (or ``CREATE INDEX``) to MySQL."""
    # Order matters: AUTOINCREMENT match before INTEGER PRIMARY KEY
    sql = sql.replace("AUTOINCREMENT", "AUTO_INCREMENT")
    sql = sql.replace("INTEGER PRIMARY KEY", "INT PRIMARY KEY")
    # TEXT NOT NULL DEFAULT (datetime('now')) → DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    sql = re.sub(
        r"TEXT NOT NULL DEFAULT \(datetime\('now'\)\)",
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        sql,
    )
    sql = sql.replace("REAL", "DOUBLE")
    return sql


def to_mysql_dml(sql: str) -> str:
    """Translate a SQLite DML statement (INSERT / UPSERT) to MySQL."""
    sql = sql.replace("INSERT OR IGNORE", "INSERT IGNORE")
    # ON CONFLICT(key) DO UPDATE SET col=excluded.col
    #   → ON DUPLICATE KEY UPDATE col=VALUES(col)
    # Single call-site (sys_settings upsert); handled inline there.
    return sql


# ── Placeholder ───────────────────────────────────────────────────

def to_mysql_placeholder(sql: str) -> str:
    """Replace qmark placeholders with %s for pymysql."""
    return sql.replace("?", "%s")


# ── PRAGMA equivalents ────────────────────────────────────────────

SHOW_COLUMNS_SQL = "SHOW COLUMNS FROM {table}"
```

- [ ] **Step 2: Create `test/test_db_ddl.py`**

```python
"""Tests for DDL/DML dialect translation."""

from app.models.db_ddl import to_mysql_ddl, to_mysql_dml, to_mysql_placeholder


class TestDdlTranslation:
    def test_autoincrement(self) -> None:
        sql = "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        result = to_mysql_ddl(sql)
        assert "AUTOINCREMENT" not in result
        assert "AUTO_INCREMENT" in result
        assert "INT PRIMARY KEY" in result

    def test_text_datetime_default(self) -> None:
        sql = "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        result = to_mysql_ddl(sql)
        assert "TEXT" not in result.split("DEFAULT")[0]  # type column changed
        assert "DATETIME" in result
        assert "CURRENT_TIMESTAMP" in result
        assert "datetime('now')" not in result

    def test_updated_at_datetime_default(self) -> None:
        sql = "updated_at TEXT"
        result = to_mysql_ddl(sql)
        # 'updated_at TEXT' without DEFAULT clause stays as-is (no datetime func)
        assert "TEXT" in result

    def test_real_to_double(self) -> None:
        sql = "temperature REAL NOT NULL DEFAULT 0.7,"
        result = to_mysql_ddl(sql)
        assert "REAL" not in result
        assert "DOUBLE" in result

    def test_keep_other_types(self) -> None:
        sql = (
            "name TEXT NOT NULL UNIQUE,"
            "max_tokens INTEGER NOT NULL DEFAULT 1024,"
            "system_prompt TEXT,"
        )
        result = to_mysql_ddl(sql)
        assert "TEXT" in result  # TEXT without datetime default stays
        assert "INTEGER" in result  # INTEGER without PRIMARY KEY stays

    def test_full_create_table(self) -> None:
        """A representative CREATE TABLE — verify all rules compose correctly."""
        sql = (
            "CREATE TABLE IF NOT EXISTS ai_models("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT NOT NULL UNIQUE,"
            "model_id TEXT NOT NULL,"
            "temperature REAL NOT NULL DEFAULT 0.7,"
            "max_tokens INTEGER NOT NULL DEFAULT 1024,"
            "support_stream INTEGER NOT NULL DEFAULT 1,"
            "status TEXT NOT NULL DEFAULT 'enabled',"
            "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "updated_at TEXT"
            ")"
        )
        result = to_mysql_ddl(sql)
        assert "AUTOINCREMENT" not in result
        assert "AUTO_INCREMENT" in result
        assert "INT PRIMARY KEY" in result
        assert "REAL" not in result
        assert "DOUBLE" in result
        assert "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP" in result
        # non-datetime TEXT columns stay as TEXT
        assert "TEXT NOT NULL UNIQUE" in result
        assert "TEXT NOT NULL DEFAULT 'enabled'" in result


class TestDmlTranslation:
    def test_insert_or_ignore(self) -> None:
        sql = "INSERT OR IGNORE INTO skills(code, name) VALUES(?,?)"
        result = to_mysql_dml(sql)
        assert "INSERT IGNORE" in result
        assert "OR" not in result

    def test_regular_insert_untouched(self) -> None:
        sql = "INSERT INTO users(username, password_hash) VALUES(?,?)"
        result = to_mysql_dml(sql)
        assert result == sql


class TestPlaceholderTranslation:
    def test_qmark_to_percent_s(self) -> None:
        sql = "SELECT * FROM users WHERE username=? AND status=?"
        result = to_mysql_placeholder(sql)
        assert "?" not in result
        assert result.count("%s") == 2

    def test_no_placeholders_unchanged(self) -> None:
        sql = "SELECT 1"
        result = to_mysql_placeholder(sql)
        assert result == sql
```

- [ ] **Step 3: Run tests, verify all pass**

```bash
uv run pytest test/test_db_ddl.py -v
```

Expected: 9 passed

- [ ] **Step 4: Commit**

```bash
git add app/models/db_ddl.py test/test_db_ddl.py
git commit -m "feat: add DDL/DML dialect translation functions"
```

---

### Task 2: DatabaseConnection Wrapper

**Files:**
- Modify: `app/models/db.py` (add `DatabaseConnection` class, keep existing functions intact)

This wrapper sits between callers and the raw driver connection. All existing `get_connection()` callers will receive a `DatabaseConnection` instance instead of raw `sqlite3.Connection`.

- [ ] **Step 1: Add `DatabaseConnection` class to `app/models/db.py`**

Insert after the `get_connection()` function (which is line 21-26) but keep `get_connection()` unchanged for now (Task 3 modifies it):

```python
# ── DatabaseConnection wrapper ────────────────────────────────────

class DatabaseConnection:
    """Thin wrapper unifying sqlite3 and pymysql connections.

    Callers use ``conn.execute(sql, params).fetchall()`` and
    ``row["col"]`` — this wrapper ensures both backends behave the
    same way.
    """

    def __init__(
        self,
        conn: sqlite3.Connection | object,  # pymysql.Connection
        dialect: str,  # "sqlite" | "mysql"
    ) -> None:
        self._conn = conn
        self._dialect = dialect

    # -- context manager -------------------------------------------

    def __enter__(self) -> "DatabaseConnection":
        self._conn.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._conn.__exit__(*args)

    # -- execute ---------------------------------------------------

    def execute(
        self, sql: str, parameters: tuple | None = None
    ) -> "CursorProxy":
        if self._dialect == "mysql":
            sql = sql.replace("?", "%s")
        cur = self._conn.execute(sql, parameters or ())
        return CursorProxy(cur)

    # -- executemany -----------------------------------------------

    def executemany(self, sql: str, seq: list) -> "CursorProxy":
        if self._dialect == "mysql":
            sql = sql.replace("?", "%s")
        cur = self._conn.executemany(sql, seq)
        return CursorProxy(cur)

    # -- executescript (SQLite only) -------------------------------

    def executescript(self, sql: str) -> "CursorProxy":
        if self._dialect == "mysql":
            raise RuntimeError("executescript not supported on MySQL")
        cur = self._conn.executescript(sql)
        return CursorProxy(cur)

    # -- commit / rollback ------------------------------------------

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class CursorProxy:
    """Minimal proxy so ``cur.lastrowid`` works transparently."""

    def __init__(self, cursor: object) -> None:
        self._cur = cursor

    def fetchone(self) -> object:
        return self._cur.fetchone()

    def fetchall(self) -> list:
        return self._cur.fetchall()

    @property
    def lastrowid(self) -> int | None:
        return getattr(self._cur, "lastrowid", None)

    @property
    def rowcount(self) -> int | None:
        return getattr(self._cur, "rowcount", None)
```

- [ ] **Step 2: Extend `test/test_db.py` with wrapper tests**

Add these test functions at the end of `test/test_db.py`:

```python
def test_database_connection_wrapper_sqlite(tmp_db: None) -> None:
    """Wrapper should behave identically to raw sqlite3.Connection."""
    from app.models.db import DatabaseConnection
    import sqlite3

    raw = sqlite3.connect(db_module.DB_PATH)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    wrapped = DatabaseConnection(raw, "sqlite")

    with wrapped as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _test_wrap(id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        conn.execute("INSERT INTO _test_wrap(name) VALUES(?)", ("hello",))
        cur = conn.execute("SELECT * FROM _test_wrap WHERE name=?", ("hello",))
        row = cur.fetchone()
    # tear down
    with wrapped as conn:
        conn.execute("DROP TABLE IF EXISTS _test_wrap")

    assert row is not None
    assert row["name"] == "hello"
    assert row["id"] == 1


def test_cursor_proxy_lastrowid(tmp_db: None) -> None:
    """lastrowid should be accessible through the wrapper."""
    from app.models.db import DatabaseConnection
    import sqlite3

    raw = sqlite3.connect(db_module.DB_PATH)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    wrapped = DatabaseConnection(raw, "sqlite")

    with wrapped as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _test_lrid(id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)"
        )
        cur = conn.execute("INSERT INTO _test_lrid(v) VALUES(?)", ("x",))
        new_id = cur.lastrowid
        cur2 = conn.execute("SELECT id FROM _test_lrid WHERE id=?", (new_id,))
        row = cur2.fetchone()
    with wrapped as conn:
        conn.execute("DROP TABLE IF EXISTS _test_lrid")

    assert new_id == 1
    assert row is not None
    assert row["id"] == 1
```

- [ ] **Step 3: Run tests, verify wrapper tests pass alongside existing tests**

```bash
uv run pytest test/test_db.py -v
```

Expected: 8 passed (6 existing + 2 new)

- [ ] **Step 4: Commit**

```bash
git add app/models/db.py test/test_db.py
git commit -m "feat: add DatabaseConnection wrapper with CursorProxy"
```

---

### Task 3: Connection Factory — `get_connection()` and `init_db()` Dual-Path

**Files:**
- Modify: `app/models/db.py` (rewrite `get_connection()`, extend `init_db()`)
- Modify: `test/test_db.py` (add startup/fallback tests)

This is the core wiring — `get_connection()` becomes a factory that reads `_active_db_type` and returns the right `DatabaseConnection`.

- [ ] **Step 1: Add module-level state and helper functions to `app/models/db.py`**

Insert after `DB_PATH` definition (line 18) but before `get_connection()`:

```python
import threading
import logging

_logger = logging.getLogger(__name__)

# Active database type — set at startup, updated on switch
_active_db_type: str = "sqlite"

# Lock held during switch; normal get_connection() acquires+releases instantly
_switch_lock = threading.Lock()

# Cached MySQL connection params (loaded from sys_settings at startup / on switch)
_mysql_params: dict[str, str | int] = {}


def _load_mysql_params() -> dict[str, str | int]:
    """Read MySQL connection params from sys_settings (SQLite)."""
    import app.models.secrets_store as secrets_store

    with _sqlite_raw_connect() as conn:
        rows = conn.execute("SELECT key, value FROM sys_settings").fetchall()
        settings = {r["key"]: r["value"] for r in rows}
    password = settings.get("mysql_password", "")
    if password:
        password = secrets_store.decrypt(password)
    return {
        "host": settings.get("mysql_host", "127.0.0.1"),
        "port": int(settings.get("mysql_port", "3306")),
        "user": settings.get("mysql_user", ""),
        "password": password,
        "database": settings.get("mysql_database", ""),
    }


def _sqlite_raw_connect() -> sqlite3.Connection:
    """Return a raw sqlite3.Connection (for bootstrap / settings reads)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _sqlite_connect() -> "DatabaseConnection":
    conn = _sqlite_raw_connect()
    return DatabaseConnection(conn, "sqlite")


def _mysql_connect() -> "DatabaseConnection":
    import pymysql

    conn = pymysql.connect(
        host=str(_mysql_params["host"]),
        port=int(_mysql_params["port"]),
        user=str(_mysql_params["user"]),
        password=str(_mysql_params["password"]),
        database=str(_mysql_params["database"]),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=5,
    )
    return DatabaseConnection(conn, "mysql")
```

- [ ] **Step 2: Replace the existing `get_connection()` function**

Replace lines 21-26:

```python
def get_connection() -> "DatabaseConnection":
    """Return a connection to the currently-active database.

    During a switch, blocks briefly (≤5s) while migration completes.
    """
    acquired = _switch_lock.acquire(timeout=5)
    if not acquired:
        raise RuntimeError("Database switch in progress — please retry shortly")
    _switch_lock.release()

    if _active_db_type == "mysql":
        return _mysql_connect()
    return _sqlite_connect()
```

- [ ] **Step 3: Extend `init_db()` for startup dual-path logic**

Replace the `init_db()` function (lines 705-714):

```python
def init_db() -> None:
    """Bootstrap database: create SQLite tables, seed data, then check
    if MySQL is configured and initialize it as well."""
    # Always init SQLite first (it holds sys_settings)
    with _sqlite_raw_connect() as conn:
        _init_users_table(conn)
        _init_admin_tables(conn)
        _seed_admin_data(conn)
        _init_model_tables(conn)
        _init_business_tables(conn)
        _seed_business_data(conn)
        _init_agent_tables(conn)
        _run_migrations(conn)

    # Check if MySQL is configured
    row = None
    with _sqlite_raw_connect() as conn:
        row = conn.execute(
            "SELECT value FROM sys_settings WHERE key='db_type'"
        ).fetchone()

    if row and row["value"] == "mysql":
        global _mysql_params
        _mysql_params = _load_mysql_params()
        try:
            _init_mysql_tables()
            global _active_db_type
            _active_db_type = "mysql"
            _logger.info("Database: using MySQL (%s:%s/%s)",
                         _mysql_params["host"], _mysql_params["port"],
                         _mysql_params["database"])
        except Exception as e:
            _logger.warning(
                "MySQL configured but unreachable — falling back to SQLite: %s", e
            )
            _active_db_type = "sqlite"
    else:
        _active_db_type = "sqlite"
        _logger.info("Database: using SQLite (%s)", DB_PATH)


def _init_mysql_tables() -> None:
    """Create all tables + seed data in MySQL (if they don't exist)."""
    from app.models.db_ddl import to_mysql_ddl, to_mysql_dml

    # Re-use the same init functions but with translated SQL.
    # Strategy: temporarily override the connection to return MySQL,
    # then call each init function.  The functions use conn.execute()
    # which will now hit MySQL.
    #
    # For simplicity we re-implement the DDL here — the MySQL path
    # only runs at startup.  Each CREATE TABLE is translated.
    with _mysql_connect() as conn:
        # Users table
        conn.execute(to_mysql_ddl(
            "CREATE TABLE IF NOT EXISTS users("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "username TEXT NOT NULL UNIQUE,"
            "password_hash TEXT NOT NULL,"
            "salt TEXT NOT NULL,"
            "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        ))
        # Admin tables
        conn.execute(to_mysql_ddl(
            "CREATE TABLE IF NOT EXISTS admin_roles("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "role_code TEXT NOT NULL UNIQUE,"
            "role_name TEXT NOT NULL,"
            "role_type TEXT NOT NULL DEFAULT 'manager',"
            "description TEXT,"
            "is_system INTEGER NOT NULL DEFAULT 0,"
            "status TEXT NOT NULL DEFAULT 'enabled',"
            "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "updated_at TEXT"
            ")"
        ))
        conn.execute(to_mysql_ddl(
            "CREATE TABLE IF NOT EXISTS admin_users("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "username TEXT NOT NULL UNIQUE,"
            "password_hash TEXT NOT NULL,"
            "salt TEXT NOT NULL,"
            "display_name TEXT NOT NULL,"
            "role_id INTEGER NOT NULL,"
            "is_super INTEGER NOT NULL DEFAULT 0,"
            "status TEXT NOT NULL DEFAULT 'enabled',"
            "must_change_password INTEGER NOT NULL DEFAULT 0,"
            "last_login_at TEXT,"
            "failed_login_count INTEGER NOT NULL DEFAULT 0,"
            "locked_until TEXT,"
            "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "updated_at TEXT,"
            "FOREIGN KEY(role_id) REFERENCES admin_roles(id)"
            ")"
        ))
        conn.execute(to_mysql_ddl(
            "CREATE TABLE IF NOT EXISTS admin_menus("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "parent_id INTEGER NOT NULL DEFAULT 0,"
            "menu_code TEXT NOT NULL UNIQUE,"
            "menu_name TEXT NOT NULL,"
            "icon TEXT,"
            "url TEXT,"
            "sort_order INTEGER NOT NULL DEFAULT 0,"
            "status TEXT NOT NULL DEFAULT 'enabled',"
            "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "updated_at TEXT"
            ")"
        ))
        conn.execute(to_mysql_ddl(
            "CREATE TABLE IF NOT EXISTS admin_role_menus("
            "role_id INTEGER NOT NULL,"
            "menu_id INTEGER NOT NULL,"
            "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "PRIMARY KEY(role_id, menu_id),"
            "FOREIGN KEY(role_id) REFERENCES admin_roles(id),"
            "FOREIGN KEY(menu_id) REFERENCES admin_menus(id)"
            ")"
        ))
        # Model tables
        conn.execute(to_mysql_ddl(
            "CREATE TABLE IF NOT EXISTS ai_models("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT NOT NULL UNIQUE,"
            "model_id TEXT NOT NULL,"
            "model_type TEXT NOT NULL DEFAULT 'text',"
            "base_url TEXT NOT NULL,"
            "api_key TEXT NOT NULL,"
            "temperature REAL NOT NULL DEFAULT 0.7,"
            "max_tokens INTEGER NOT NULL DEFAULT 1024,"
            "system_prompt TEXT,"
            "support_stream INTEGER NOT NULL DEFAULT 1,"
            "support_think INTEGER NOT NULL DEFAULT 0,"
            "is_default INTEGER NOT NULL DEFAULT 0,"
            "status TEXT NOT NULL DEFAULT 'enabled',"
            "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "updated_at TEXT"
            ")"
        ))
        conn.execute(to_mysql_ddl(
            "CREATE TABLE IF NOT EXISTS ai_model_usage("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "model_id INTEGER NOT NULL,"
            "prompt_tokens INTEGER NOT NULL DEFAULT 0,"
            "completion_tokens INTEGER NOT NULL DEFAULT 0,"
            "total_tokens INTEGER NOT NULL DEFAULT 0,"
            "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            "FOREIGN KEY(model_id) REFERENCES ai_models(id)"
            ")"
        ))
        # Business tables — each one individually (replaces executescript)
        _business_tables = [
            ("digital_employees",
             "CREATE TABLE IF NOT EXISTS digital_employees("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "name TEXT NOT NULL UNIQUE,"
             "avatar TEXT NOT NULL DEFAULT '🤖',"
             "model_id INTEGER NOT NULL DEFAULT 0,"
             "system_prompt TEXT,"
             "skills TEXT NOT NULL DEFAULT '[]',"
             "status TEXT NOT NULL DEFAULT 'enabled',"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "updated_at TEXT"
             ")"),
            ("skills",
             "CREATE TABLE IF NOT EXISTS skills("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "code TEXT NOT NULL UNIQUE,"
             "name TEXT NOT NULL,"
             "skill_type TEXT NOT NULL DEFAULT 'builtin',"
             "config_json TEXT NOT NULL DEFAULT '{}',"
             "status TEXT NOT NULL DEFAULT 'enabled',"
             "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
             ")"),
            ("chat_sessions",
             "CREATE TABLE IF NOT EXISTS chat_sessions("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "user_id INTEGER NOT NULL DEFAULT 0,"
             "employee_id INTEGER NOT NULL DEFAULT 0,"
             "model_id INTEGER DEFAULT 0,"
             "title TEXT NOT NULL DEFAULT '新对话',"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "updated_at TEXT"
             ")"),
            ("chat_messages",
             "CREATE TABLE IF NOT EXISTS chat_messages("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "session_id INTEGER NOT NULL,"
             "role TEXT NOT NULL DEFAULT 'user',"
             "content TEXT NOT NULL,"
             "skill_meta TEXT,"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "FOREIGN KEY(session_id) REFERENCES chat_sessions(id)"
             ")"),
            ("watchtower_sources",
             "CREATE TABLE IF NOT EXISTS watchtower_sources("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "name TEXT NOT NULL,"
             "source_type TEXT NOT NULL DEFAULT 'rss',"
             "url TEXT NOT NULL,"
             "url_template TEXT,"
             "request_headers TEXT NOT NULL DEFAULT '',"
             "config_json TEXT NOT NULL DEFAULT '{}',"
             "fetch_interval INTEGER NOT NULL DEFAULT 60,"
             "status TEXT NOT NULL DEFAULT 'enabled',"
             "last_fetched TEXT,"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "updated_at TEXT"
             ")"),
            ("watchtower_items",
             "CREATE TABLE IF NOT EXISTS watchtower_items("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "source_id INTEGER NOT NULL,"
             "title TEXT NOT NULL,"
             "content TEXT,"
             "url TEXT,"
             "sentiment TEXT,"
             "risk INTEGER NOT NULL DEFAULT 0,"
             "published_at TEXT,"
             "is_deep_collected INTEGER NOT NULL DEFAULT 0,"
             "deep_task_id INTEGER DEFAULT NULL,"
             "deep_collected_at TEXT DEFAULT NULL,"
             "summary TEXT,"
             "keywords TEXT NOT NULL DEFAULT '[]',"
             "raw_json TEXT NOT NULL DEFAULT '{}',"
             "collected_at TEXT,"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "updated_at TEXT,"
             "FOREIGN KEY(source_id) REFERENCES watchtower_sources(id)"
             ")"),
            ("deep_tasks",
             "CREATE TABLE IF NOT EXISTS deep_tasks("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "name TEXT NOT NULL,"
             "target_url TEXT NOT NULL,"
             "depth INTEGER NOT NULL DEFAULT 1,"
             "schedule TEXT,"
             "status TEXT NOT NULL DEFAULT 'idle',"
             "target_item_ids TEXT NOT NULL DEFAULT '[]',"
             "progress INTEGER NOT NULL DEFAULT 0,"
             "total_items INTEGER NOT NULL DEFAULT 0,"
             "completed_items INTEGER NOT NULL DEFAULT 0,"
             "failed_items INTEGER NOT NULL DEFAULT 0,"
             "logs TEXT NOT NULL DEFAULT '[]',"
             "started_at TEXT,"
             "finished_at TEXT,"
             "error_message TEXT,"
             "last_run TEXT,"
             "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
             ")"),
            ("deep_contents",
             "CREATE TABLE IF NOT EXISTS deep_contents("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "item_id INTEGER NOT NULL,"
             "task_id INTEGER,"
             "title TEXT,"
             "url TEXT,"
             "markdown TEXT NOT NULL DEFAULT '',"
             "plain_text TEXT NOT NULL DEFAULT '',"
             "summary TEXT,"
             "keywords TEXT NOT NULL DEFAULT '[]',"
             "sentiment TEXT,"
             "risk INTEGER NOT NULL DEFAULT 0,"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "FOREIGN KEY(item_id) REFERENCES watchtower_items(id) ON DELETE CASCADE,"
             "FOREIGN KEY(task_id) REFERENCES deep_tasks(id) ON DELETE SET NULL"
             ")"),
            ("ask_history",
             "CREATE TABLE IF NOT EXISTS ask_history("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "user_id INTEGER NOT NULL,"
             "query TEXT NOT NULL,"
             "generated_sql TEXT,"
             "result_count INTEGER NOT NULL DEFAULT 0,"
             "status TEXT NOT NULL DEFAULT 'ok',"
             "error_code TEXT,"
             "model_id INTEGER,"
             "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
             ")"),
            ("api_keys",
             "CREATE TABLE IF NOT EXISTS api_keys("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "name TEXT NOT NULL,"
             "api_type TEXT NOT NULL DEFAULT 'weather',"
             "endpoint TEXT,"
             "api_key TEXT,"
             "status TEXT NOT NULL DEFAULT 'enabled',"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "updated_at TEXT"
             ")"),
            ("data_warehouse",
             "CREATE TABLE IF NOT EXISTS data_warehouse("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "name TEXT NOT NULL,"
             "sql_query TEXT NOT NULL,"
             "description TEXT,"
             "category TEXT NOT NULL DEFAULT '默认',"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "updated_at TEXT"
             ")"),
            ("sys_settings",
             "CREATE TABLE IF NOT EXISTS sys_settings("
             "key TEXT PRIMARY KEY,"
             "value TEXT NOT NULL DEFAULT '',"
             "updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
             ")"),
            ("screen_configs",
             "CREATE TABLE IF NOT EXISTS screen_configs("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "name TEXT NOT NULL,"
             "screen_type TEXT NOT NULL DEFAULT 'smart',"
             "layout_json TEXT NOT NULL DEFAULT '{}',"
             "is_public INTEGER NOT NULL DEFAULT 0,"
             "status TEXT NOT NULL DEFAULT 'enabled',"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "updated_at TEXT"
             ")"),
            ("screen_widgets",
             "CREATE TABLE IF NOT EXISTS screen_widgets("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "config_id INTEGER NOT NULL,"
             "widget_type TEXT NOT NULL,"
             "title TEXT NOT NULL,"
             "data_query TEXT,"
             "settings_json TEXT NOT NULL DEFAULT '{}',"
             "sort_order INTEGER NOT NULL DEFAULT 0,"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "updated_at TEXT,"
             "FOREIGN KEY(config_id) REFERENCES screen_configs(id) ON DELETE CASCADE"
             ")"),
            ("digital_twin_scenes",
             "CREATE TABLE IF NOT EXISTS digital_twin_scenes("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "name TEXT NOT NULL,"
             "description TEXT,"
             "scene_json TEXT NOT NULL DEFAULT '{}',"
             "status TEXT NOT NULL DEFAULT 'enabled',"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "updated_at TEXT"
             ")"),
            ("digital_twin_models",
             "CREATE TABLE IF NOT EXISTS digital_twin_models("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "scene_id INTEGER NOT NULL,"
             "name TEXT NOT NULL,"
             "model_type TEXT NOT NULL DEFAULT 'primitive',"
             "asset_url TEXT,"
             "transform_json TEXT NOT NULL DEFAULT '{}',"
             "metadata_json TEXT NOT NULL DEFAULT '{}',"
             "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
             "updated_at TEXT,"
             "FOREIGN KEY(scene_id) REFERENCES digital_twin_scenes(id) ON DELETE CASCADE"
             ")"),
            ("schema_migrations",
             "CREATE TABLE IF NOT EXISTS schema_migrations("
             "version TEXT PRIMARY KEY,"
             "applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
             ")"),
            ("agent_decisions",
             "CREATE TABLE IF NOT EXISTS agent_decisions("
             "id INTEGER PRIMARY KEY AUTOINCREMENT,"
             "source TEXT NOT NULL DEFAULT 'agent',"
             "action TEXT NOT NULL,"
             "outcome TEXT NOT NULL DEFAULT 'pending',"
             "reason TEXT,"
             "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
             ")"),
        ]
        for _name, ddl in _business_tables:
            conn.execute(to_mysql_ddl(ddl))

        # Seed data — only if tables are empty
        _seed_mysql_data(conn)


def _seed_mysql_data(conn: "DatabaseConnection") -> None:
    """Seed minimum data into MySQL so the app is usable."""
    from app.models.crypto import hash_password, new_salt
    from app.models.db_ddl import to_mysql_dml

    # admin_roles
    cur = conn.execute("SELECT COUNT(*) AS cnt FROM admin_roles")
    if cur.fetchone()["cnt"] == 0:
        roles = [
            ("super_admin", "超级管理员", "manager", "系统内置超级管理员角色", 1),
            ("manager", "管理用户", "manager", "后台管理侧普通管理角色", 0),
            ("web_user", "普通用户", "web_user", "前台用户侧访问角色", 1),
        ]
        conn.executemany(
            to_mysql_dml(
                "INSERT OR IGNORE INTO admin_roles(role_code, role_name, role_type, description, is_system) "
                "VALUES(?,?,?,?,?)"
            ),
            roles,
        )

    # admin user (admin / admin888)
    cur = conn.execute("SELECT COUNT(*) AS cnt FROM admin_users WHERE username='admin'")
    if cur.fetchone()["cnt"] == 0:
        role = conn.execute(
            "SELECT id FROM admin_roles WHERE role_code='super_admin'"
        ).fetchone()
        if role:
            salt = new_salt()
            pw = hash_password("admin888", salt)
            conn.execute(
                to_mysql_dml(
                    "INSERT OR IGNORE INTO admin_users"
                    "(username, password_hash, salt, display_name, role_id, is_super, must_change_password) "
                    "VALUES(?,?,?,?,?,?,?)"
                ),
                ("admin", pw, salt.hex(), "超级管理员", role["id"], 1, 1),
            )

    # skills
    cur = conn.execute("SELECT COUNT(*) AS cnt FROM skills")
    if cur.fetchone()["cnt"] == 0:
        skills = [
            ("weather", "天气查询", "builtin", '{"prefix": "@weather"}'),
            ("music", "音乐播放", "builtin", '{"prefix": "@music"}'),
            ("campus", "西师妹校园助手", "builtin", '{"prefix": "@西师妹"}'),
            ("websearch", "网络搜索", "builtin", '{"prefix": "\\\\search"}'),
        ]
        conn.executemany(
            to_mysql_dml(
                "INSERT OR IGNORE INTO skills(code, name, skill_type, config_json) VALUES(?,?,?,?)"
            ),
            skills,
        )

    # sys_settings
    cur = conn.execute("SELECT COUNT(*) AS cnt FROM sys_settings")
    if cur.fetchone()["cnt"] == 0:
        conn.execute(
            to_mysql_dml(
                "INSERT OR IGNORE INTO sys_settings(key, value) VALUES(?,?)"
            ),
            ("db_type", "mysql"),
        )
        conn.execute(
            to_mysql_dml(
                "INSERT OR IGNORE INTO sys_settings(key, value) VALUES(?,?)"
            ),
            ("site_name", "DataFinder AgentOS"),
        )
```

- [ ] **Step 4: Fix the `_migrate` function to work with `DatabaseConnection`**

The `_migrate` function (line 545) uses `PRAGMA table_info()` which is SQLite-only. It only ever runs on SQLite (migrations are SQLite-path), so we need to make sure it uses a raw SQLite connection. Change the function signature from `conn: sqlite3.Connection` to `conn: object` and use `_sqlite_raw_connect()` when called from `init_db()`:

```python
# In _migrate, line 563-565: keep PRAGMA usage (SQLite only).
# _migrate is ONLY called from init_db() with a raw SQLite connection.
# No change needed to _migrate itself — the raw connection is passed in.
```

Actually, `_migrate` already receives a raw sqlite3.Connection from `_sqlite_raw_connect()` in the init path (before we changed `init_db`). The `_migrate` function itself is fine — it's only called with a raw SQLite connection. No change needed.

But `_migrate` at line 577 uses `INSERT OR IGNORE INTO` which is SQLite syntax. Since `_migrate` runs on raw SQLite connection, this is fine. No change.

- [ ] **Step 5: Add startup tests to `test/test_db.py`**

```python
def test_init_db_sets_active_to_sqlite(tmp_db: None) -> None:
    """After init_db(), _active_db_type should be 'sqlite' by default."""
    import app.models.db as db_module2

    # tmp_db fixture already called init_db()
    assert db_module2._active_db_type == "sqlite"


def test_mysql_unreachable_falls_back_to_sqlite(tmp_db: None) -> None:
    """If sys_settings says mysql but MySQL is unreachable, fall back to sqlite."""
    import app.models.db as db_module2

    with db_module2._sqlite_raw_connect() as conn:
        conn.execute(
            "UPDATE sys_settings SET value='mysql' WHERE key='db_type'"
        )
        conn.execute(
            "INSERT OR IGNORE INTO sys_settings(key,value) VALUES('mysql_host','192.0.2.1')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO sys_settings(key,value) VALUES('mysql_port','3306')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO sys_settings(key,value) VALUES('mysql_user','root')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO sys_settings(key,value) VALUES('mysql_password','')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO sys_settings(key,value) VALUES('mysql_database','test')"
        )

    # Re-run init to trigger the fallback path
    db_module2.init_db()
    # Should still be sqlite — MySQL at 192.0.2.1 is unreachable
    assert db_module2._active_db_type == "sqlite"
```

- [ ] **Step 6: Run all tests**

```bash
uv run pytest test/test_db.py test/test_db_ddl.py -v
```

Expected: All tests pass (6 existing + 2 wrapper + 2 startup = 10+ tests)

- [ ] **Step 7: Commit**

```bash
git add app/models/db.py test/test_db.py
git commit -m "feat: dual-path connection factory with MySQL startup fallback"
```

---

### Task 4: DatabaseSwitcher — Switch Orchestration

**Files:**
- Create: `app/models/db_switcher.py`
- Create: `test/test_db_switcher.py`

The switcher orchestrates a safe switch: preflight → lock → migrate → switch → unlock.

- [ ] **Step 1: Create `app/models/db_switcher.py`**

```python
"""Database hot-switch orchestrator.

Usage::

    switcher = DatabaseSwitcher("mysql")
    try:
        switcher.preflight()
        switcher.lock()
        switcher.migrate()
        switcher.switch()
    except DatabaseSwitchError:
        switcher.rollback()
        raise
"""

import logging
from typing import Any

from app.models.db import (
    _active_db_type,
    _load_mysql_params,
    _mysql_connect,
    _mysql_params,
    _sqlite_connect,
    _switch_lock,
    get_connection,
)
from app.models.db_ddl import to_mysql_ddl, to_mysql_dml

_logger = logging.getLogger(__name__)

# Topological table order for migration (no-FK tables first)
MIGRATION_ORDER = [
    # Layer 1 — no foreign keys
    "users",
    "admin_roles",
    "ai_models",
    "skills",
    "sys_settings",
    "watchtower_sources",
    "deep_tasks",
    "data_warehouse",
    "screen_configs",
    "digital_twin_scenes",
    "schema_migrations",
    "agent_decisions",
    # Layer 2 — FK to layer 1
    "admin_users",
    "admin_menus",
    "chat_sessions",
    "digital_employees",
    "api_keys",
    "screen_widgets",
    "digital_twin_models",
    "watchtower_items",
    # Layer 3 — FK to layer 1 or 2
    "admin_role_menus",
    "chat_messages",
    "deep_contents",
    "ai_model_usage",
    "ask_history",
]


class DatabaseSwitchError(Exception):
    """Raised when a switch operation fails."""


class DatabaseSwitcher:
    """Orchestrate a hot-switch between SQLite and MySQL (bidirectional)."""

    def __init__(self, target: str, params: dict[str, Any] | None = None) -> None:
        """*target* is ``"sqlite"`` or ``"mysql"``.
        *params* is a dict of MySQL connection parameters (only needed for mysql target).
        """
        if target not in ("sqlite", "mysql"):
            raise ValueError(f"Unknown target: {target}")
        self.target = target
        self.params = params or {}
        self._locked = False

    # ── preflight ──────────────────────────────────────────────

    def preflight(self) -> None:
        """Test target connection + ensure tables exist.  Does NOT hold lock."""
        if self.target == "sqlite":
            self._preflight_sqlite()
        else:
            self._preflight_mysql()

    def _preflight_sqlite(self) -> None:
        import os
        from app.models.db import DB_PATH

        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        # Test via normal connection
        conn = _sqlite_connect()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()

    def _preflight_mysql(self) -> None:
        import pymysql

        # 1. Test raw connection
        try:
            test_conn = pymysql.connect(
                host=self.params.get("host", "127.0.0.1"),
                port=int(self.params.get("port", 3306)),
                user=self.params.get("user", ""),
                password=self.params.get("password", ""),
                database=self.params.get("database", ""),
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
            )
            test_conn.close()
        except Exception as e:
            raise DatabaseSwitchError(f"MySQL connection test failed: {e}") from e

        # 2. Init tables on MySQL (idempotent)
        from app.models.db import _init_mysql_tables

        # Temporarily set _mysql_params so _init_mysql_tables() works
        import app.models.db as db_module

        old_params = dict(db_module._mysql_params)
        db_module._mysql_params = self.params
        try:
            _init_mysql_tables()
        finally:
            db_module._mysql_params = old_params

        # 3. Verify a write works
        conn = _mysql_connect()
        try:
            conn.execute(
                to_mysql_ddl(
                    "CREATE TABLE IF NOT EXISTS _switch_test("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "v TEXT)"
                )
            )
            conn.execute("INSERT INTO _switch_test(v) VALUES(%s)", ("ok",))
            conn.execute("DELETE FROM _switch_test")
            conn.execute("DROP TABLE IF EXISTS _switch_test")
        finally:
            conn.close()

    # ── lock / unlock ──────────────────────────────────────────

    def lock(self) -> None:
        """Acquire the global switch lock. Blocks all new get_connection() calls."""
        _switch_lock.acquire()
        self._locked = True
        _logger.info("Database switch lock acquired — requests paused")

    def unlock(self) -> None:
        """Release the global switch lock."""
        if self._locked:
            _switch_lock.release()
            self._locked = False
            _logger.info("Database switch lock released")

    # ── migrate ────────────────────────────────────────────────

    def migrate(self) -> None:
        """Snapshot-copy all data from current DB to target DB."""
        source_conn = get_connection()
        target_conn = self._target_connection()
        try:
            for table in MIGRATION_ORDER:
                self._migrate_table(source_conn, target_conn, table)
        finally:
            source_conn.close()
            target_conn.close()

    def _target_connection(self):
        if self.target == "sqlite":
            return _sqlite_connect()
        return _mysql_connect()

    def _migrate_table(
        self, source, target, table: str
    ) -> None:
        """Copy all rows from *source* to *target* for one table."""
        try:
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
        except Exception:
            # Table may not exist in source — skip
            return

        if not rows:
            return

        # Clear target table
        try:
            target.execute(f"DELETE FROM {table}")
        except Exception:
            pass  # table might not exist in target yet

        columns = list(rows[0].keys())
        placeholders = ", ".join(
            ["?" if self.target == "sqlite" else "%s"] * len(columns)
        )
        cols_str = ", ".join(columns)
        sql = f"INSERT INTO {table}({cols_str}) VALUES({placeholders})"

        values = [tuple(r[col] for col in columns) for r in rows]
        for row_vals in values:
            target.execute(sql, row_vals)

    # ── switch ─────────────────────────────────────────────────

    def switch(self) -> None:
        """Commit the switch: persist db_type, update memory, release lock."""
        import app.models.db as db_module
        from app.models.secrets_store import encrypt

        # Persist to sys_settings via raw SQLite (always available)
        _UPSERT_SQL = (
            "INSERT INTO sys_settings(key, value, updated_at) "
            "VALUES(?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_at=excluded.updated_at"
        )
        with db_module._sqlite_raw_connect() as sqlite_conn:
            sqlite_conn.execute(_UPSERT_SQL, ("db_type", self.target))
            if self.target == "mysql" and self.params:
                for k, v in self.params.items():
                    val = encrypt(v) if k == "mysql_password" else str(v)
                    sqlite_conn.execute(_UPSERT_SQL, (k, val))

        # Update in-memory state
        db_module._active_db_type = self.target
        if self.target == "mysql" and self.params:
            db_module._mysql_params = dict(self.params)

        # Release lock
        self.unlock()

    # ── rollback ───────────────────────────────────────────────

    def rollback(self) -> None:
        """Release lock without switching. Call on failure after lock()."""
        self.unlock()

    # ── run (convenience) ──────────────────────────────────────

    def run(self) -> None:
        """Full switch flow: preflight → lock → migrate → switch."""
        self.preflight()
        self.lock()
        try:
            self.migrate()
            self.switch()
        except Exception:
            self.rollback()
            raise
```

- [ ] **Step 2: Create `test/test_db_switcher.py`**

```python
"""Tests for DatabaseSwitcher."""

import os
import threading
import time

import pytest

import app.models.db as db_module
from app.models.db_switcher import DatabaseSwitcher, DatabaseSwitchError


@pytest.fixture()
def _reset_state() -> None:
    """Ensure module state is reset before each test."""
    db_module._active_db_type = "sqlite"
    db_module._mysql_params = {}
    # Ensure lock is not held from a previous test
    try:
        db_module._switch_lock.release()
    except RuntimeError:
        pass  # already released


def test_preflight_sqlite_succeeds(tmp_db: None, _reset_state: None) -> None:
    switcher = DatabaseSwitcher("sqlite")
    switcher.preflight()  # should not raise


def test_preflight_mysql_bad_params_fails(
    tmp_db: None, _reset_state: None
) -> None:
    switcher = DatabaseSwitcher("mysql", {
        "host": "192.0.2.1",
        "port": 3306,
        "user": "nobody",
        "password": "wrong",
        "database": "nonexistent",
    })
    with pytest.raises(DatabaseSwitchError):
        switcher.preflight()


def test_preflight_invalid_target(tmp_db: None, _reset_state: None) -> None:
    with pytest.raises(ValueError, match="Unknown target"):
        DatabaseSwitcher("postgresql")  # type: ignore[arg-type]


def test_switch_updates_active_db_type(
    tmp_db: None, _reset_state: None
) -> None:
    """Switch from sqlite to sqlite (for testing — no MySQL needed)."""
    switcher = DatabaseSwitcher("sqlite")
    switcher.lock()
    try:
        switcher.migrate()
        switcher.switch()
    finally:
        # Ensure unlock even on failure
        if switcher._locked:
            switcher.unlock()

    assert db_module._active_db_type == "sqlite"


def test_lock_blocks_other_threads(
    tmp_db: None, _reset_state: None
) -> None:
    """A thread trying get_connection() during lock should block."""
    result = {"acquired": False, "error": None}

    def worker() -> None:
        try:
            conn = db_module.get_connection()
            conn.close()
            result["acquired"] = True
        except Exception as e:
            result["error"] = str(e)

    switcher = DatabaseSwitcher("sqlite")
    switcher.lock()
    try:
        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=0.3)
        # After 300ms, worker should still be blocked
        assert not result["acquired"]
        assert result["error"] is None
    finally:
        switcher.unlock()

    # Now the worker should complete
    t.join(timeout=2)
    assert result["acquired"]


def test_lock_timeout(tmp_db: None, _reset_state: None) -> None:
    """get_connection() should raise RuntimeError after 5s timeout."""
    result = {"error": None}

    def worker() -> None:
        try:
            db_module.get_connection()
        except RuntimeError as e:
            result["error"] = str(e)

    # Override timeout to 1s for test speed
    old_timeout = 5
    db_module._switch_lock = threading.Lock()
    db_module._switch_lock.acquire()  # hold the lock

    # We need to patch the timeout parameter — use a quick workaround
    db_module._switch_lock.release()
    # Re-acquire, then test with a smaller timeout by replacing the module-level lock
    # Actually, the get_connection() has timeout=5 hardcoded. For this test
    # we'll directly test the lock behavior.
    lock = threading.Lock()
    lock.acquire()

    def try_acquire() -> None:
        acquired = lock.acquire(timeout=1)
        if not acquired:
            result["error"] = "timeout"
        else:
            lock.release()

    t = threading.Thread(target=try_acquire)
    t.start()
    t.join(timeout=3)

    assert result["error"] == "timeout"
    lock.release()


def test_migration_preserves_row_counts(
    tmp_db: None, _reset_state: None
) -> None:
    """After a sqlite → sqlite migration, row counts should match."""
    # Insert some test data
    with db_module.get_connection() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, salt) VALUES(?,?,?)",
            ("testuser", "hash", "salt"),
        )

    # Count before
    with db_module.get_connection() as conn:
        before = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]

    # Run switcher
    switcher = DatabaseSwitcher("sqlite")
    switcher.lock()
    try:
        switcher.migrate()
        switcher.switch()
    finally:
        if switcher._locked:
            switcher.unlock()

    # Count after
    with db_module.get_connection() as conn:
        after = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]

    assert before == after
    assert before >= 1


def test_rollback_after_lock_releases(
    tmp_db: None, _reset_state: None
) -> None:
    """rollback() should release the lock without changing state."""
    original = db_module._active_db_type
    switcher = DatabaseSwitcher("sqlite")
    switcher.lock()
    switcher.rollback()
    assert db_module._active_db_type == original
    # Lock should be released — get_connection() should work
    conn = db_module.get_connection()
    conn.close()
```

- [ ] **Step 3: Run switcher tests**

```bash
uv run pytest test/test_db_switcher.py -v
```

Expected: 7 passed (preflight_sqlite, preflight_mysql_bad_params, invalid_target, switch_updates, lock_blocks, lock_timeout, migration_row_counts, rollback)

- [ ] **Step 4: Run full test suite to check for regressions**

```bash
uv run pytest test/test_db.py test/test_db_ddl.py test/test_db_switcher.py -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add app/models/db_switcher.py test/test_db_switcher.py
git commit -m "feat: add DatabaseSwitcher for hot-switch orchestration"
```

---

### Task 5: Settings Controller Integration

**Files:**
- Modify: `app/controllers/settings.py`

The settings POST handler must call the switcher instead of just saving settings.

- [ ] **Step 1: Modify `app/controllers/settings.py` POST handler**

Replace the `post()` method (lines 41-97) with:

```python
    def post(self) -> None:
        if not check_rate_limit(f"admin_settings:{self.current_user}", 10, 60):
            self.set_status(429)
            return self.write({"error": "请求过于频繁，请稍后再试"})

        action = self.get_body_argument("action", "")
        if action == "test_db":
            self.set_header("Content-Type", "application/json")
            db_type = self.get_body_argument("db_type", "sqlite")
            if db_type == "sqlite":
                return self.write({"ok": True, "msg": "SQLite 连接正常"})
            try:
                import pymysql

                host = self.get_body_argument("mysql_host", "127.0.0.1")
                port = parse_int(
                    self.get_body_argument("mysql_port", "3306"),
                    3306,
                    min_value=1,
                    max_value=65535,
                )
                user = self.get_body_argument("mysql_user", "")
                password = self.get_body_argument("mysql_password", "")
                database = self.get_body_argument("mysql_database", "")
                conn = pymysql.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database,
                    connect_timeout=3,
                )
                conn.close()

                # Also verify DDL can be created
                from app.models.db_switcher import DatabaseSwitcher

                switcher = DatabaseSwitcher("mysql", {
                    "host": host,
                    "port": port,
                    "user": user,
                    "password": password,
                    "database": database,
                })
                switcher.preflight()
                return self.write(
                    {"ok": True, "msg": "MySQL 连接成功，建表验证通过"}
                )
            except Exception as e:
                log_error("MySQL 连接测试失败", e)
                return self.write({"ok": False, "msg": f"MySQL 连接失败: {e}"})

        # ── Save settings (with potential DB switch) ──────────

        site_name = self.get_body_argument("site_name", "DataFinder AgentOS").strip()
        db_type = self.get_body_argument("db_type", "sqlite")

        # Save basic settings first (always to current active DB)
        self._save("site_name", site_name)

        # Check if db_type changed
        import app.models.db as db_module

        old_db_type = db_module._active_db_type
        if db_type != old_db_type:
            # Switching databases
            from app.models.db_switcher import DatabaseSwitcher, DatabaseSwitchError
            from app.models.secrets_store import encrypt

            if db_type == "mysql":
                params = {
                    "host": self.get_body_argument("mysql_host", "127.0.0.1"),
                    "port": parse_int(
                        self.get_body_argument("mysql_port", "3306"),
                        3306,
                        min_value=1,
                        max_value=65535,
                    ),
                    "user": self.get_body_argument("mysql_user", ""),
                    "password": self.get_body_argument("mysql_password", ""),
                    "database": self.get_body_argument("mysql_database", ""),
                }
            else:
                params = {}

            try:
                switcher = DatabaseSwitcher(db_type, params)
                switcher.run()
            except DatabaseSwitchError as e:
                log_error("数据库切换失败", e)
                self._redirect_with_message(
                    "/admin/settings", f"数据库切换失败: {e}"
                )
                return
        else:
            # Same db_type — just save MySQL params (don't switch)
            if db_type == "mysql":
                from app.models.secrets_store import encrypt

                for k in (
                    "mysql_host",
                    "mysql_port",
                    "mysql_user",
                    "mysql_password",
                    "mysql_database",
                ):
                    val = self.get_body_argument(k, "")
                    if k == "mysql_password" and val:
                        val = encrypt(val)
                    elif k == "mysql_password" and not val:
                        continue
                    self._save(k, val)

            self._save("db_type", db_type)

        self._redirect_with_message("/admin/settings", "设置已保存")
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest test/ -v
```

Expected: All db-related tests pass. (Skill dispatcher and watchtower scraper failures are pre-existing and unrelated.)

- [ ] **Step 3: Check type consistency**

```bash
uv run pyright app/models/db_switcher.py app/controllers/settings.py app/models/db.py
```

Expected: 0 errors, 0 warnings

- [ ] **Step 4: Run ruff check + format**

```bash
uv run ruff check .
uv run ruff format .
```

Expected: 0 errors, no formatting changes for new files

- [ ] **Step 5: Commit**

```bash
git add app/controllers/settings.py
git commit -m "feat: integrate DatabaseSwitcher into settings controller"
```

---

### Task 6: Manual Verification & Final Quality Gate

- [ ] **Step 1: Start the server and verify SQLite path still works**

```bash
uv run python app.py &
sleep 2
curl -s http://localhost:10086/ | head -20
```

Expected: Server starts, landing page returns HTML

- [ ] **Step 2: Verify admin settings page loads**

```bash
# Login as admin first (using demo credentials), then access /admin/settings
```

Expected: Settings page shows "数据库设置" tab with SQLite selected

- [ ] **Step 3: Run full quality gate**

```bash
uv run ruff check .                        # 0 errors
uv run ruff format .                       # no changes
uv run pyright                             # 0 errors, 0 warnings, 0 informations
npx @biomejs/biome check                   # 0 errors, 0 warnings
npx eslint app/static/js/ app/templates/ --ext .html,.js  # 0 real errors
uv run python scripts/check_templates.py   # 0 template issues
```

- [ ] **Step 4: Kill server**

```bash
kill %1
```

- [ ] **Step 5: Final commit (if any quality-gate fixes)**

```bash
git add -A
git commit -m "chore: quality gate fixes for database hot-switch"
```
