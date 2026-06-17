import json
import sqlite3
from app.models.db import get_connection

class EmployeeRepository:
    @staticmethod
    def list_employees(keyword='', page=1):
        per_page = 20
        offset = (page - 1) * per_page
        like = f'%{keyword}%'
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM digital_employees WHERE name LIKE ?", (like,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT de.*, m.name AS model_name FROM digital_employees de "
                "LEFT JOIN ai_models m ON m.id=de.model_id "
                "WHERE de.name LIKE ? ORDER BY de.id DESC LIMIT ? OFFSET ?",
                (like, per_page, offset)
            ).fetchall()
        return rows, total

    @staticmethod
    def list_all_active():
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM digital_employees WHERE status='enabled' ORDER BY id ASC"
            ).fetchall()

    @staticmethod
    def get_employee(emp_id):
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM digital_employees WHERE id=?", (emp_id,)
            ).fetchone()

    @staticmethod
    def create_employee(name, avatar, model_id, system_prompt, skills_list, status):
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO digital_employees(name, avatar, model_id, system_prompt, skills, status) VALUES(?,?,?,?,?,?)",
                    (name, avatar, model_id, system_prompt, json.dumps(skills_list, ensure_ascii=False), status)
                )
            return True, None
        except sqlite3.IntegrityError as e:
            return False, str(e)

    @staticmethod
    def update_employee(emp_id, name, avatar, model_id, system_prompt, skills_list, status):
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE digital_employees SET name=?, avatar=?, model_id=?, system_prompt=?, skills=?, status=?, updated_at=datetime('now') WHERE id=?",
                    (name, avatar, model_id, system_prompt, json.dumps(skills_list, ensure_ascii=False), status, emp_id)
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_employee(emp_id):
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM digital_employees WHERE id=?", (emp_id,))
            return True, None
        except Exception as e:
            return False, str(e)
