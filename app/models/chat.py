from app.models.db import get_connection


class ChatRepository:
    @staticmethod
    def create_session(user_id, employee_id, title):
        try:
            with get_connection() as conn:
                cur = conn.execute(
                    "INSERT INTO chat_sessions(user_id, employee_id, title) VALUES(?,?,?)",
                    (user_id, employee_id, title),
                )
                return cur.lastrowid, None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def get_session(session_id):
        with get_connection() as conn:
            return conn.execute(
                """SELECT s.*, u.username,
                          COALESCE(e.name, '-') AS employee_name
                   FROM chat_sessions s
                   LEFT JOIN users u ON s.user_id = u.id
                   LEFT JOIN digital_employees e ON s.employee_id = e.id
                   WHERE s.id=?""",
                (session_id,),
            ).fetchone()

    @staticmethod
    def list_sessions(user_id, page=1):
        per_page = 20
        offset = (page - 1) * per_page
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM chat_sessions WHERE user_id=?", (user_id,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM chat_sessions WHERE user_id=? ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
                (user_id, per_page, offset),
            ).fetchall()
        return rows, total

    @staticmethod
    def update_session_title(session_id, title):
        with get_connection() as conn:
            conn.execute(
                "UPDATE chat_sessions SET title=?, updated_at=datetime('now') WHERE id=?",
                (title, session_id),
            )

    @staticmethod
    def delete_session(session_id):
        with get_connection() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))

    @staticmethod
    def delete_sessions(session_ids, user_id):
        with get_connection() as conn:
            placeholders = ",".join("?" for _ in session_ids)
            params = list(session_ids) + [user_id]
            conn.execute(
                f"DELETE FROM chat_messages WHERE session_id IN "
                f"(SELECT id FROM chat_sessions WHERE id IN ({placeholders}) AND user_id=?)",
                params,
            )
            cur = conn.execute(
                f"DELETE FROM chat_sessions WHERE id IN ({placeholders}) AND user_id=?",
                params,
            )
            return cur.rowcount

    @staticmethod
    def add_message(session_id, role, content, skill_meta=None):
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO chat_messages(session_id, role, content, skill_meta) VALUES(?,?,?,?)",
                (session_id, role, content, skill_meta),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at=datetime('now') WHERE id=?",
                (session_id,),
            )
            return cur.lastrowid

    @staticmethod
    def list_messages(session_id):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id ASC",
                (session_id,),
            ).fetchall()

    @staticmethod
    def count_all_sessions():
        with get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0]

    @staticmethod
    def count_all_messages():
        with get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]

    @staticmethod
    def list_all_sessions(page=1, per_page=20):
        offset = (page - 1) * per_page
        with get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0]
            rows = conn.execute(
                """SELECT s.*, u.username,
                   COALESCE(e.name, '-') AS employee_name,
                   (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS msg_count
                   FROM chat_sessions s
                   LEFT JOIN users u ON s.user_id = u.id
                   LEFT JOIN digital_employees e ON s.employee_id = e.id
                   ORDER BY s.id DESC LIMIT ? OFFSET ?""",
                (per_page, offset),
            ).fetchall()
        return rows, total
