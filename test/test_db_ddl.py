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
        assert "INSERT OR" not in result

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
