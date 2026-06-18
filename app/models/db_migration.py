"""Database migration: SQLite -> MySQL schema export and data transfer."""

from app.models.db import _sqlite_raw_connect
from app.models.db_ddl import to_mysql_ddl


class DatabaseMigrator:
    """Export SQLite schema as MySQL DDL and migrate data in batches."""

    @staticmethod
    def export_schema_to_mysql() -> list[str]:
        """Export all SQLite tables as MySQL CREATE TABLE statements."""
        ddl_list: list[str] = []
        with _sqlite_raw_connect() as conn:
            tables = conn.execute(
                "SELECT name, sql FROM sqlite_master"
                " WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
                " ORDER BY name"
            ).fetchall()
            for row in tables:
                mysql_ddl = to_mysql_ddl(row["sql"])
                mysql_ddl = (
                    mysql_ddl.rstrip(";").rstrip(")")
                    + ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
                )
                ddl_list.append(mysql_ddl)
        return ddl_list

    @staticmethod
    def migrate_table_data(
        table_name: str,
        mysql_params: dict,
        batch_size: int = 1000,
    ) -> tuple[int, int]:
        """Migrate one table: returns (success_rows, failed_rows)."""
        import pymysql
        from app.models.errors import log_error

        success = 0
        failed = 0

        with _sqlite_raw_connect() as sqlite_conn:
            total = sqlite_conn.execute(
                f"SELECT COUNT(*) as cnt FROM [{table_name}]"
            ).fetchone()["cnt"]
            if total == 0:
                return 0, 0

            columns_info = sqlite_conn.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()
            columns = [c["name"] for c in columns_info]

            for offset in range(0, total, batch_size):
                rows = sqlite_conn.execute(
                    f"SELECT * FROM [{table_name}] LIMIT ? OFFSET ?",
                    (batch_size, offset),
                ).fetchall()
                if not rows:
                    break

                try:
                    mysql_conn = pymysql.connect(
                        host=str(mysql_params["host"]),
                        port=int(mysql_params["port"]),
                        user=str(mysql_params["user"]),
                        password=str(mysql_params["password"]),
                        database=str(mysql_params["database"]),
                        cursorclass=pymysql.cursors.DictCursor,
                        connect_timeout=10,
                    )
                    placeholders = ", ".join(["%s"] * len(columns))
                    cols_str = ", ".join(columns)
                    sql = f"INSERT IGNORE INTO {table_name}({cols_str}) VALUES({placeholders})"

                    with mysql_conn.cursor() as cursor:
                        values = [tuple(dict(r).values()) for r in rows]
                        cursor.executemany(sql, values)
                    mysql_conn.commit()
                    mysql_conn.close()
                    success += len(rows)
                except Exception as e:
                    log_error(f"migrate_table_data {table_name} offset={offset}", e)
                    failed += len(rows)

        return success, failed

    @staticmethod
    async def migrate_all_tables(
        mysql_params: dict,
    ) -> dict[str, tuple[int, int]]:
        """Migrate all tables; returns {table: (success, failed)}."""
        from tornado.ioloop import IOLoop

        with _sqlite_raw_connect() as conn:
            all_tables = [
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master"
                    " WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            ]

        results: dict[str, tuple[int, int]] = {}
        for table in all_tables:
            s, f = await IOLoop.current().run_in_executor(
                None,
                DatabaseMigrator.migrate_table_data,
                table,
                mysql_params,
                1000,
            )
            results[table] = (s, f)
        return results
