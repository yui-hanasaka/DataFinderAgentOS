from app.models.db import get_connection


class SourceRepository:
    @staticmethod
    def list_sources(keyword="", page=1):
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
    def get_source(src_id):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM watchtower_sources WHERE id=?", (src_id,)
            ).fetchone()

    @staticmethod
    def create_source(name, source_type, url, fetch_interval, status):
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO watchtower_sources(name, source_type, url, fetch_interval, status) VALUES(?,?,?,?,?)",
                    (name, source_type, url, fetch_interval, status),
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def update_source(src_id, name, source_type, url, fetch_interval, status):
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE watchtower_sources SET name=?, source_type=?, url=?, fetch_interval=?, status=? WHERE id=?",
                    (name, source_type, url, fetch_interval, status, src_id),
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_source(src_id):
        try:
            with get_connection() as conn:
                conn.execute(
                    "DELETE FROM watchtower_items WHERE source_id=?", (src_id,)
                )
                conn.execute("DELETE FROM watchtower_sources WHERE id=?", (src_id,))
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def mark_fetched(src_id):
        with get_connection() as conn:
            conn.execute(
                "UPDATE watchtower_sources SET last_fetched=datetime('now') WHERE id=?",
                (src_id,),
            )


class ItemRepository:
    @staticmethod
    def add_item(source_id, title, content, url, published_at):
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO watchtower_items(source_id, title, content, url, published_at)
                   VALUES(?,?,?,?,?)""",
                (source_id, title, content, url, published_at),
            )
            return cur.lastrowid

    @staticmethod
    def list_items(source_id=None, page=1, per_page=20):
        offset = (page - 1) * per_page
        with get_connection() as conn:
            if source_id:
                total = conn.execute(
                    "SELECT COUNT(*) FROM watchtower_items WHERE source_id=?",
                    (source_id,),
                ).fetchone()[0]
                rows = conn.execute(
                    """SELECT i.*, s.name AS source_name FROM watchtower_items i
                       LEFT JOIN watchtower_sources s ON i.source_id=s.id
                       WHERE i.source_id=? ORDER BY i.id DESC LIMIT ? OFFSET ?""",
                    (source_id, per_page, offset),
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
    def update_sentiment(item_id, sentiment, risk):
        with get_connection() as conn:
            conn.execute(
                "UPDATE watchtower_items SET sentiment=?, risk=? WHERE id=?",
                (sentiment, risk, item_id),
            )

    @staticmethod
    def count_items():
        with get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM watchtower_items").fetchone()[0]

    @staticmethod
    def recent_items(limit=10):
        with get_connection() as conn:
            return conn.execute(
                """SELECT i.*, s.name AS source_name FROM watchtower_items i
                   LEFT JOIN watchtower_sources s ON i.source_id=s.id
                   ORDER BY i.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()

    @staticmethod
    def get_item(item_id):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM watchtower_items WHERE id=?", (item_id,)
            ).fetchone()
