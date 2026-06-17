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
