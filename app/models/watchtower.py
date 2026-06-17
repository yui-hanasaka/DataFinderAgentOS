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
    def create_source(
        name: str,
        source_type: str,
        url: str,
        fetch_interval: int,
        status: str,
        url_template: str = "",
        request_headers: str = "",
        config_json: str = "{}",
    ) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO watchtower_sources(name, source_type, url, fetch_interval,
                       status, url_template, request_headers, config_json)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        name,
                        source_type,
                        url,
                        fetch_interval,
                        status,
                        url_template,
                        request_headers,
                        config_json,
                    ),
                )
            return True, None
        except Exception:
            return False, "创建采集源失败"

    @staticmethod
    def update_source(
        source_id: int,
        name: str,
        source_type: str,
        url: str,
        fetch_interval: int,
        status: str,
        url_template: str = "",
        request_headers: str = "",
        config_json: str = "{}",
    ) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    """UPDATE watchtower_sources SET name=?, source_type=?, url=?,
                       fetch_interval=?, status=?, url_template=?, request_headers=?,
                       config_json=?, updated_at=datetime('now') WHERE id=?""",
                    (
                        name,
                        source_type,
                        url,
                        fetch_interval,
                        status,
                        url_template,
                        request_headers,
                        config_json,
                        source_id,
                    ),
                )
            return True, None
        except Exception:
            return False, "更新采集源失败"

    @staticmethod
    def delete_source(source_id: int) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "DELETE FROM watchtower_items WHERE source_id=?", (source_id,)
                )
                conn.execute("DELETE FROM watchtower_sources WHERE id=?", (source_id,))
            return True, None
        except Exception:
            return False, "删除采集源失败"

    @staticmethod
    def mark_fetched(source_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE watchtower_sources SET last_fetched=datetime('now') WHERE id=?",
                (source_id,),
            )

    @staticmethod
    def list_all_enabled() -> list[sqlite3.Row]:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM watchtower_sources WHERE status='enabled' ORDER BY id ASC"
            ).fetchall()


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

    @staticmethod
    def batch_add_items(items: list[dict]) -> int:
        """批量保存采集条目，返回成功插入数量"""
        count = 0
        with get_connection() as conn:
            for item in items:
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO watchtower_items
                           (source_id, title, content, url, published_at, keywords, raw_json)
                           VALUES(?,?,?,?,?,?,?)""",
                        (
                            item["source_id"],
                            item["title"],
                            item.get("content", ""),
                            item.get("url", ""),
                            item.get("published_at", ""),
                            item.get("keywords", "[]"),
                            item.get("raw_json", "{}"),
                        ),
                    )
                    if conn.total_changes:
                        count += 1
                except Exception:
                    pass
        return count
