import json
import sqlite3

from app.models.db import get_connection


class EmployeeRepository:
    @staticmethod
    def list_employees(
        keyword: str = "", page: int = 1
    ) -> tuple[list[sqlite3.Row], int]:
        per_page = 20
        offset = (page - 1) * per_page
        like = f"%{keyword}%"
        with get_connection() as conn:
            total = int(
                conn.execute(
                    "SELECT COUNT(*) FROM digital_employees WHERE name LIKE ?", (like,)
                ).fetchone()[0]
            )
            rows = conn.execute(
                "SELECT de.*, m.name AS model_name FROM digital_employees de "
                "LEFT JOIN ai_models m ON m.id=de.model_id "
                "WHERE de.name LIKE ? ORDER BY de.id DESC LIMIT ? OFFSET ?",
                (like, per_page, offset),
            ).fetchall()
        return rows, total

    @staticmethod
    def list_all_active() -> list[sqlite3.Row]:
        with get_connection() as conn:
            return conn.execute(
                "SELECT de.*, m.name AS model_name"
                " FROM digital_employees de"
                " LEFT JOIN ai_models m ON m.id = de.model_id"
                " WHERE de.status='enabled' ORDER BY de.id ASC"
            ).fetchall()

    @staticmethod
    def get_employee(employee_id: int) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM digital_employees WHERE id=?", (employee_id,)
            ).fetchone()

    @staticmethod
    def create_employee(data: dict[str, object]) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO digital_employees(name, avatar, model_id, system_prompt, skills, status) VALUES(?,?,?,?,?,?)",
                    (
                        data["name"],
                        data["avatar"],
                        data["model_id"],
                        data["system_prompt"],
                        json.dumps(data["skills_list"], ensure_ascii=False),
                        data["status"],
                    ),
                )
            return True, None
        except sqlite3.IntegrityError as e:
            return False, str(e)

    @staticmethod
    def update_employee(
        employee_id: int, data: dict[str, object]
    ) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE digital_employees SET name=?, avatar=?, model_id=?, system_prompt=?, skills=?, status=?, updated_at=datetime('now') WHERE id=?",
                    (
                        data["name"],
                        data["avatar"],
                        data["model_id"],
                        data["system_prompt"],
                        json.dumps(data["skills_list"], ensure_ascii=False),
                        data["status"],
                        employee_id,
                    ),
                )
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_employee(employee_id: int) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM digital_employees WHERE id=?", (employee_id,))
            return True, None
        except Exception as e:
            return False, str(e)
