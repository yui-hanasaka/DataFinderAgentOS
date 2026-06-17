import sqlite3

from app.models.db import get_connection


class SourceRepository:
    @staticmethod
    def list_sources(keyword: str = "", page: int = 1) -> tuple[list[sqlite3.Row], int]:
        per_page = 20
        offset = (page - 1) * per_page
        like = f"%{keyword}%"
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM watchtower_sources WHERE name LIKE ?", (like,)
            ).fetchone()[0]
            rows = conn.execute(
                """SELECT s.*, (SELECT COUNT(*) FROM watchtower_items WHERE source_id=s.id) AS item_count
                   FROM watchtower_sources s WHERE s.name LIKE ? ORDER BY s.id DESC LIMIT ? OFFSET ?""",
                (like, per_page, offset),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_source(source_id: int) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM watchtower_sources WHERE id=?", (source_id,)
            ).fetchone()

    @staticmethod
    def create_source(data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO watchtower_sources(name, source_type, url, fetch_interval, status) VALUES(?,?,?,?,?)",
                    (
                        data["name"],
                        data["source_type"],
                        data["url"],
                        data["fetch_interval"],
                        data["status"],
                    ),
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def update_source(
        source_id: int, data: dict[str, object]
    ) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE watchtower_sources SET name=?, source_type=?, url=?, fetch_interval=?, status=? WHERE id=?",
                    (
                        data["name"],
                        data["source_type"],
                        data["url"],
                        data["fetch_interval"],
                        data["status"],
                        source_id,
                    ),
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_source(source_id: int) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "DELETE FROM watchtower_items WHERE source_id=?", (source_id,)
                )
                conn.execute("DELETE FROM watchtower_sources WHERE id=?", (source_id,))
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def mark_fetched(source_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE watchtower_sources SET last_fetched=datetime('now') WHERE id=?",
                (source_id,),
            )


class ItemRepository:
    @staticmethod
    def add_item(data: dict[str, object]) -> int | None:
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO watchtower_items(source_id, title, content, url, published_at)
                   VALUES(?,?,?,?,?)""",
                (
                    data["source_id"],
                    data["title"],
                    data["content"],
                    data["url"],
                    data["published_at"],
                ),
            )
            return cur.lastrowid

    @staticmethod
    def list_items(keyword: str = "", page: int = 1) -> tuple[list[sqlite3.Row], int]:
        per_page = 20
        offset = (page - 1) * per_page
        like = f"%{keyword}%"
        with get_connection() as conn:
            if keyword:
                total = conn.execute(
                    "SELECT COUNT(*) FROM watchtower_items WHERE title LIKE ? OR content LIKE ?",
                    (like, like),
                ).fetchone()[0]
                rows = conn.execute(
                    """SELECT i.*, s.name AS source_name FROM watchtower_items i
                       LEFT JOIN watchtower_sources s ON i.source_id=s.id
                       WHERE i.title LIKE ? OR i.content LIKE ?
                       ORDER BY i.id DESC LIMIT ? OFFSET ?""",
                    (like, like, per_page, offset),
                ).fetchall()
            else:
                total = conn.execute(
                    "SELECT COUNT(*) FROM watchtower_items"
                ).fetchone()[0]
                rows = conn.execute(
                    """SELECT i.*, s.name AS source_name FROM watchtower_items i
                       LEFT JOIN watchtower_sources s ON i.source_id=s.id
                       ORDER BY i.id DESC LIMIT ? OFFSET ?""",
                    (per_page, offset),
                ).fetchall()
        return rows, total

    @staticmethod
    def update_sentiment(item_id: int, sentiment: str, risk: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE watchtower_items SET sentiment=?, risk=? WHERE id=?",
                (sentiment, risk, item_id),
            )

    @staticmethod
    def count_items(keyword: str = "") -> int:
        with get_connection() as conn:
            if keyword:
                like = f"%{keyword}%"
                return conn.execute(
                    "SELECT COUNT(*) FROM watchtower_items WHERE title LIKE ? OR content LIKE ?",
                    (like, like),
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM watchtower_items").fetchone()[0]

    @staticmethod
    def recent_items(limit: int = 12) -> list[sqlite3.Row]:
        with get_connection() as conn:
            return conn.execute(
                """SELECT i.*, s.name AS source_name FROM watchtower_items i
                   LEFT JOIN watchtower_sources s ON i.source_id=s.id
                   ORDER BY i.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()

    @staticmethod
    def get_item(item_id: int) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM watchtower_items WHERE id=?", (item_id,)
            ).fetchone()
