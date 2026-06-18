import sqlite3

from app.models.db import get_connection


class SkillRepository:
    @staticmethod
    def list_skills(keyword: str = "", page: int = 1) -> tuple[list[sqlite3.Row], int]:
        per_page = 20
        offset = (page - 1) * per_page
        like = f"%{keyword}%"
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM skills WHERE name LIKE ? OR code LIKE ?",
                (like, like),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM skills WHERE name LIKE ? OR code LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (like, like, per_page, offset),
            ).fetchall()
        return rows, total

    @staticmethod
    def list_all_active() -> list[sqlite3.Row]:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM skills WHERE status='enabled' ORDER BY id ASC"
            ).fetchall()

    @staticmethod
    def get_skill(skill_id: int) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM skills WHERE id=?", (skill_id,)
            ).fetchone()

    @staticmethod
    def get_skill_by_code(code: str) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute("SELECT * FROM skills WHERE code=?", (code,)).fetchone()

    @staticmethod
    def create_skill(data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO skills(code, name, skill_type, description,"
                    " api_url, http_method, parameters_json, headers_json,"
                    " config_json, status) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        data["code"],
                        data["name"],
                        data["skill_type"],
                        data.get("description", ""),
                        data.get("api_url", ""),
                        data.get("http_method", "GET"),
                        data.get("parameters_json", "[]"),
                        data.get("headers_json", "{}"),
                        data.get("config_json", "{}"),
                        data["status"],
                    ),
                )
            return True, None
        except sqlite3.IntegrityError as e:
            return False, str(e)

    @staticmethod
    def update_skill(skill_id: int, data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE skills SET name=?, skill_type=?, description=?,"
                    " api_url=?, http_method=?, parameters_json=?, headers_json=?,"
                    " config_json=?, status=?, updated_at=datetime('now')"
                    " WHERE id=?",
                    (
                        data["name"],
                        data["skill_type"],
                        data.get("description", ""),
                        data.get("api_url", ""),
                        data.get("http_method", "GET"),
                        data.get("parameters_json", "[]"),
                        data.get("headers_json", "{}"),
                        data.get("config_json", "{}"),
                        data["status"],
                        skill_id,
                    ),
                )
            return True, None
        except sqlite3.IntegrityError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_skill(skill_id: int) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
            return True, None
        except Exception as e:
            return False, str(e)
