import json
import sqlite3

from app.models.db import get_connection


class EmployeeRepository:
    _SKILL_TO_TOOL: dict[str, str] = {
        "web_search": "web_search",
        "code_exec": "code_execute",
        "watchtower": "watchtower_search",
        "warehouse": "warehouse_query",
        "deep_crawl": "deep_collect",
        "env_check": "env_info",
    }

    @staticmethod
    def get_employee_with_tools(employee_id: int) -> dict | None:
        """Return employee dict with allowed_tools derived from skills field."""
        from app.models.db import get_connection

        emp_row = EmployeeRepository.get_employee(employee_id)
        if not emp_row:
            return None

        skills_raw = emp_row["skills"] or "[]"
        try:
            skills_data = json.loads(skills_raw)
        except (json.JSONDecodeError, TypeError):
            skills_data = []

        if isinstance(skills_data, list):
            skill_ids = skills_data
            force_task_agent = False
            task_config: dict = {}
        elif isinstance(skills_data, dict):
            skill_ids = skills_data.get("skill_ids", [])
            force_task_agent = skills_data.get("force_task_agent", False)
            task_config = skills_data.get("task_config", {})
        else:
            skill_ids = []
            force_task_agent = False
            task_config = {}

        allowed_tools: list[str] = []
        if skill_ids:
            with get_connection() as conn:
                placeholders = ",".join(["?"] * len(skill_ids))
                rows = conn.execute(
                    f"SELECT code FROM skills WHERE id IN ({placeholders}) AND status='enabled'",
                    skill_ids,
                ).fetchall()
                for row in rows:
                    tool_name = EmployeeRepository._SKILL_TO_TOOL.get(row["code"])
                    if tool_name and tool_name not in allowed_tools:
                        allowed_tools.append(tool_name)

        result = dict(emp_row)
        result["allowed_tools"] = allowed_tools if allowed_tools else None
        result["force_task_agent"] = force_task_agent
        result["task_config"] = task_config
        return result

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
