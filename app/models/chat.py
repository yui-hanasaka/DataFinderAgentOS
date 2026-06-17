import sqlite3

from app.models.db import get_connection
from app.models.errors import log_error


class ChatRepository:
    @staticmethod
    def create_session(
        user_id: int, employee_id: int, title: str, model_id: int = 0
    ) -> tuple[int | None, str | None]:
        try:
            with get_connection() as conn:
                cur = conn.execute(
                    "INSERT INTO chat_sessions(user_id, employee_id, title, model_id) VALUES(?,?,?,?)",
                    (user_id, employee_id, title, model_id),
                )
                return cur.lastrowid, None
        except Exception as e:
            log_error("创建会话失败", e)
            return None, "创建会话失败"

    @staticmethod
    def get_session(session_id: int) -> sqlite3.Row | None:
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
    def list_sessions(user_id: int, page: int = 1) -> tuple[list[sqlite3.Row], int]:
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
    def update_session_employee(session_id: int, employee_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE chat_sessions SET employee_id=?, model_id=0, updated_at=datetime('now') WHERE id=?",
                (employee_id, session_id),
            )

    @staticmethod
    def update_session_model(session_id: int, model_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE chat_sessions SET model_id=?, updated_at=datetime('now') WHERE id=?",
                (model_id, session_id),
            )

    @staticmethod
    def update_session_title(session_id: int, title: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE chat_sessions SET title=?, updated_at=datetime('now') WHERE id=?",
                (title, session_id),
            )

    @staticmethod
    def delete_session(session_id: int) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))

    @staticmethod
    def delete_sessions(session_ids: list[int], user_id: int) -> int:
        with get_connection() as conn:
            placeholders = ",".join("?" for _ in session_ids)
            params: list[int] = list(session_ids) + [user_id]
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
    def delete_sessions_admin(session_ids: list[int]) -> int:
        """Batch delete sessions without user_id filtering (admin use)."""
        if not session_ids:
            return 0
        with get_connection() as conn:
            placeholders = ",".join("?" for _ in session_ids)
            conn.execute(
                f"DELETE FROM chat_messages WHERE session_id IN ({placeholders})",
                session_ids,
            )
            cur = conn.execute(
                f"DELETE FROM chat_sessions WHERE id IN ({placeholders})",
                session_ids,
            )
            return cur.rowcount

    @staticmethod
    def add_message(
        session_id: int, role: str, content: str, skill_meta: str | None = None
    ) -> int | None:
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
    def list_messages(session_id: int) -> list[sqlite3.Row]:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id ASC",
                (session_id,),
            ).fetchall()

    @staticmethod
    def count_all_sessions(keyword: str = "") -> int:
        with get_connection() as conn:
            if keyword.strip():
                like = f"%{keyword.strip()}%"
                return conn.execute(
                    """SELECT COUNT(*) FROM chat_sessions s
                       LEFT JOIN users u ON s.user_id = u.id
                       WHERE s.title LIKE ? OR u.username LIKE ?""",
                    (like, like),
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0]

    @staticmethod
    def count_all_messages() -> int:
        with get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]

    @staticmethod
    def list_all_sessions(
        page: int = 1, per_page: int = 20, keyword: str = ""
    ) -> tuple[list[sqlite3.Row], int]:
        offset = (page - 1) * per_page
        with get_connection() as conn:
            if keyword.strip():
                like = f"%{keyword.strip()}%"
                total = conn.execute(
                    """SELECT COUNT(*) FROM chat_sessions s
                       LEFT JOIN users u ON s.user_id = u.id
                       WHERE s.title LIKE ? OR u.username LIKE ?""",
                    (like, like),
                ).fetchone()[0]
                rows = conn.execute(
                    """SELECT s.*, u.username,
                       COALESCE(e.name, '-') AS employee_name,
                       (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS msg_count
                       FROM chat_sessions s
                       LEFT JOIN users u ON s.user_id = u.id
                       LEFT JOIN digital_employees e ON s.employee_id = e.id
                       WHERE s.title LIKE ? OR u.username LIKE ?
                       ORDER BY s.id DESC LIMIT ? OFFSET ?""",
                    (like, like, per_page, offset),
                ).fetchall()
            else:
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
