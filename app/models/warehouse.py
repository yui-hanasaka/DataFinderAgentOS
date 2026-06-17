from app.models.db import get_connection

class WarehouseRepository:
    @staticmethod
    def list_queries(keyword='', page=1):
        per_page = 20
        offset = (page - 1) * per_page
        like = f'%{keyword}%'
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM data_warehouse WHERE name LIKE ? OR description LIKE ?", (like, like)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM data_warehouse WHERE name LIKE ? OR description LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (like, like, per_page, offset)
            ).fetchall()
        return rows, total

    @staticmethod
    def list_all():
        with get_connection() as conn:
            return conn.execute("SELECT * FROM data_warehouse ORDER BY id ASC").fetchall()

    @staticmethod
    def get_query(q_id):
        with get_connection() as conn:
            return conn.execute("SELECT * FROM data_warehouse WHERE id=?", (q_id,)).fetchone()

    @staticmethod
    def create_query(name, sql_query, description, category):
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO data_warehouse(name, sql_query, description, category) VALUES(?,?,?,?)",
                    (name, sql_query, description, category)
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def update_query(q_id, name, sql_query, description, category):
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE data_warehouse SET name=?, sql_query=?, description=?, category=?, updated_at=datetime('now') WHERE id=?",
                    (name, sql_query, description, category, q_id)
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_query(q_id):
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM data_warehouse WHERE id=?", (q_id,))
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def execute_query(sql_query, params=None):
        stripped = sql_query.strip().upper()
        if not stripped.startswith("SELECT"):
            return None, None, "只允许执行 SELECT 查询"
        try:
            with get_connection() as conn:
                cur = conn.execute(sql_query, params or [])
                rows = cur.fetchall()
                columns = [d[0] for d in cur.description] if cur.description else []
            return rows, columns, None
        except Exception as e:
            return None, None, str(e)
