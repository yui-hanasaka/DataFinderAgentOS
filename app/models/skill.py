import sqlite3

from app.models.db import get_connection


class SkillRepository:
    @staticmethod
    def list_skills(keyword="", page=1):
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
    def list_all_active():
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM skills WHERE status='enabled' ORDER BY id ASC"
            ).fetchall()

    @staticmethod
    def get_skill(skill_id):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM skills WHERE id=?", (skill_id,)
            ).fetchone()

    @staticmethod
    def get_skill_by_code(code):
        with get_connection() as conn:
            return conn.execute("SELECT * FROM skills WHERE code=?", (code,)).fetchone()

    @staticmethod
    def create_skill(code, name, skill_type, config_json, status):
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO skills(code, name, skill_type, config_json, status) VALUES(?,?,?,?,?)",
                    (code, name, skill_type, config_json, status),
                )
            return True, None
        except sqlite3.IntegrityError as e:
            return False, str(e)

    @staticmethod
    def update_skill(skill_id, name, skill_type, config_json, status):
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE skills SET name=?, skill_type=?, config_json=?, status=? WHERE id=?",
                    (name, skill_type, config_json, status, skill_id),
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_skill(skill_id):
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
            return True, None
        except Exception as e:
            return False, str(e)
