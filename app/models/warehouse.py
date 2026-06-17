import sqlite3

from app.models.db import get_connection
from app.models.sql_guard import validate_select_sql


class WarehouseRepository:
    @staticmethod
    def list_queries(keyword: str = "", page: int = 1) -> tuple[list[sqlite3.Row], int]:
        per_page = 20
        offset = (page - 1) * per_page
        like = f"%{keyword}%"
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM data_warehouse WHERE name LIKE ? OR description LIKE ?",
                (like, like),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM data_warehouse WHERE name LIKE ? OR description LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (like, like, per_page, offset),
            ).fetchall()
        return rows, total

    @staticmethod
    def list_all() -> list[sqlite3.Row]:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM data_warehouse ORDER BY id ASC"
            ).fetchall()

    @staticmethod
    def get_query(query_id: int) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM data_warehouse WHERE id=?", (query_id,)
            ).fetchone()

    @staticmethod
    def create_query(data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO data_warehouse(name, sql_query, description, category) VALUES(?,?,?,?)",
                    (
                        data["name"],
                        data["sql_query"],
                        data["description"],
                        data["category"],
                    ),
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def update_query(query_id: int, data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE data_warehouse SET name=?, sql_query=?, description=?, category=?, updated_at=datetime('now') WHERE id=?",
                    (
                        data["name"],
                        data["sql_query"],
                        data["description"],
                        data["category"],
                        query_id,
                    ),
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_query(query_id: int) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM data_warehouse WHERE id=?", (query_id,))
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def execute_query(
        sql_query: str, params: tuple | None = None, trusted: bool = False
    ) -> tuple[list[sqlite3.Row] | None, list[str] | None, str | None]:
        if not trusted:
            ok, err = validate_select_sql(sql_query)
            if not ok:
                return None, None, err
        else:
            ok, err = WarehouseRepository._basic_sql_guard(sql_query)
            if not ok:
                return None, None, err
        try:
            with get_connection() as conn:
                cur = conn.execute(sql_query, params or [])
                rows = cur.fetchall()
                columns = [d[0] for d in cur.description] if cur.description else []
            return rows, columns, None
        except Exception:
            return None, None, "查询执行失败"

    _FORBIDDEN_KEYWORDS: tuple[str, ...] = (
        "DROP",
        "INSERT",
        "UPDATE",
        "DELETE",
        "ALTER",
        "CREATE",
        "PRAGMA",
        "ATTACH",
    )

    @staticmethod
    def _basic_sql_guard(sql: str) -> tuple[bool, str | None]:
        stripped = sql.strip()
        if not stripped.upper().startswith("SELECT"):
            return False, "仅允许执行 SELECT 查询"
        upper_sql = stripped.upper()
        for kw in WarehouseRepository._FORBIDDEN_KEYWORDS:
            if kw in upper_sql:
                return False, f"查询中包含禁止的关键字: {kw}"
        return True, None
