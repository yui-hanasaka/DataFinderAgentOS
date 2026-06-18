"""Database hot-switch orchestrator.

Usage::

    switcher = DatabaseSwitcher("mysql", params)
    switcher.run()  # preflight → lock → migrate → switch
"""

import logging
from typing import Any

import app.models.db as db_module
from app.models.db_ddl import to_mysql_ddl

_logger = logging.getLogger(__name__)

# Topological table order for migration (no-FK tables first)
MIGRATION_ORDER = [
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
    "admin_users",
    "admin_menus",
    "chat_sessions",
    "digital_employees",
    "api_keys",
    "screen_widgets",
    "digital_twin_models",
    "watchtower_items",
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
        if target not in ("sqlite", "mysql"):
            raise ValueError(f"Unknown target: {target}")
        self.target = target
        self.params = params or {}
        self._locked = False

    # ── preflight ──────────────────────────────────────────────

    def preflight(self) -> None:
        """Test target connection + ensure tables exist. Does NOT hold lock."""
        if self.target == "sqlite":
            self._preflight_sqlite()
        else:
            self._preflight_mysql()

    def _preflight_sqlite(self) -> None:
        import os
        from app.models.db import DB_PATH

        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = db_module._sqlite_connect()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()

    def _preflight_mysql(self) -> None:
        import pymysql

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

        # Init tables on MySQL (idempotent)
        old_params = dict(db_module._mysql_params)
        db_module._mysql_params = dict(self.params)
        try:
            from app.models.db import _init_mysql_tables

            _init_mysql_tables()
        finally:
            db_module._mysql_params = old_params

        # Verify a write works
        conn = db_module._mysql_connect()
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
        """Acquire the global switch lock."""
        db_module._switch_lock.acquire()
        self._locked = True
        _logger.info("Database switch lock acquired — requests paused")

    def unlock(self) -> None:
        """Release the global switch lock."""
        if self._locked:
            db_module._switch_lock.release()
            self._locked = False
            _logger.info("Database switch lock released")

    # ── migrate ────────────────────────────────────────────────

    def migrate(self) -> None:
        """Snapshot-copy all data from current DB to target DB."""
        if db_module._active_db_type == "mysql":
            source_conn = db_module._mysql_connect()
        else:
            source_conn = db_module._sqlite_connect()
        target_conn = self._target_connection()
        try:
            # Clear target tables in reverse order so FK children
            # are removed before their parents.
            for table in reversed(MIGRATION_ORDER):
                try:
                    target_conn.execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            # Copy data in forward order (FK parents first).
            for table in MIGRATION_ORDER:
                self._migrate_table(source_conn, target_conn, table)
        finally:
            source_conn.close()
            target_conn.close()

    def _target_connection(self):
        if self.target == "sqlite":
            return db_module._sqlite_connect()
        return db_module._mysql_connect()

    def _migrate_table(self, source, target, table: str) -> None:
        """Copy all rows from *source* to *target* for one table."""
        try:
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
        except Exception:
            return  # table may not exist in source

        if not rows:
            return

        columns = list(rows[0].keys())
        placeholders = ", ".join(
            ["?" if self.target == "sqlite" else "%s"] * len(columns)
        )
        cols_str = ", ".join(columns)
        sql = f"INSERT INTO {table}({cols_str}) VALUES({placeholders})"

        for row_vals in rows:
            vals = tuple(row_vals[col] for col in columns)
            target.execute(sql, vals)

    # ── switch ─────────────────────────────────────────────────

    def switch(self) -> None:
        """Commit the switch: persist db_type, update memory, release lock."""
        from app.models.secrets_store import encrypt

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

        db_module._active_db_type = self.target
        if self.target == "mysql" and self.params:
            db_module._mysql_params = dict(self.params)

        self.unlock()

    # ── rollback ───────────────────────────────────────────────

    def rollback(self) -> None:
        """Release lock without switching."""
        self.unlock()

    # ── run ────────────────────────────────────────────────────

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


def validate_mysql_connection(params: dict) -> tuple[bool, str]:
    """Validate MySQL connection params without side effects."""
    import pymysql

    try:
        conn = pymysql.connect(
            host=str(params["host"]),
            port=int(params["port"]),
            user=str(params["user"]),
            password=str(params["password"]),
            database=str(params["database"]),
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
        )
        conn.close()
        return True, "连接成功"
    except Exception as e:
        return False, f"连接失败: {e}"


def switch_to_mysql(params: dict) -> tuple[bool, str]:
    """Hot-switch to MySQL with preflight validation."""
    ok, msg = validate_mysql_connection(params)
    if not ok:
        return False, msg
    try:
        switcher = DatabaseSwitcher("mysql", params)
        switcher.run()
        return True, "已切换到MySQL"
    except Exception as e:
        return False, f"切换失败: {e}"


def switch_to_sqlite() -> tuple[bool, str]:
    """Hot-switch back to SQLite."""
    try:
        switcher = DatabaseSwitcher("sqlite")
        switcher.run()
        return True, "已切换到SQLite"
    except Exception as e:
        return False, f"切换失败: {e}"


def get_migration_status() -> dict:
    """Return current database configuration state."""
    import app.models.db as db_module

    return {
        "active_db": db_module._active_db_type,
        "mysql_configured": bool(db_module._mysql_params),
        "switch_lock_held": db_module._switch_lock.locked(),
    }
