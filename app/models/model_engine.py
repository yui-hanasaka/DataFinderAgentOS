import sqlite3
from typing import Any, overload

from app.models.db import get_connection

PER_PAGE = 6


def _page_offset(page: int, per_page: int = PER_PAGE) -> int:
    return (max(page, 1) - 1) * per_page


def _like(keyword: str) -> str:
    return f"%{keyword.strip()}%"


class ModelRepository:
    @staticmethod
    def list_models(keyword: str = "", page: int = 1, per_page: int = PER_PAGE):
        where = ""
        params = []
        if keyword.strip():
            where = "where name like ? or model_id like ? or model_type like ?"
            params = [_like(keyword), _like(keyword), _like(keyword)]
        with get_connection() as conn:
            total = conn.execute(
                f"select count(*) from ai_models {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""
				select * from ai_models
				{where}
				order by is_default desc, id desc
				limit ? offset ?
				""",
                params + [per_page, _page_offset(page, per_page)],
            ).fetchall()
        return rows, total

    @staticmethod
    def get_model(model_id: int):
        with get_connection() as conn:
            return conn.execute(
                "select * from ai_models where id=?", (model_id,)
            ).fetchone()

    @staticmethod
    def get_default_model():
        with get_connection() as conn:
            return conn.execute(
                "select * from ai_models where is_default=1 and status='enabled' order by id desc limit 1"
            ).fetchone()

    @staticmethod
    def create_model(data: dict):
        try:
            with get_connection() as conn:
                if data.get("is_default"):
                    conn.execute("update ai_models set is_default=0")
                conn.execute(
                    """
					insert into ai_models(
						name, model_id, model_type, base_url, api_key,
						temperature, max_tokens, system_prompt,
						support_stream, support_think, is_default, status
					) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
					""",
                    (
                        data["name"],
                        data["model_id"],
                        data["model_type"],
                        data["base_url"],
                        data["api_key"],
                        data["temperature"],
                        data["max_tokens"],
                        data.get("system_prompt", ""),
                        data["support_stream"],
                        data["support_think"],
                        data["is_default"],
                        data["status"],
                    ),
                )
            return True, None
        except sqlite3.IntegrityError:
            return False, "模型名称已存在"

    @staticmethod
    def update_model(model_id: int, data: dict):
        with get_connection() as conn:
            row = conn.execute(
                "select id from ai_models where id=?", (model_id,)
            ).fetchone()
            if not row:
                return False, "模型不存在"
            if data.get("is_default"):
                conn.execute(
                    "update ai_models set is_default=0 where id<>?", (model_id,)
                )
            conn.execute(
                """
				update ai_models set
					name=?, model_id=?, model_type=?, base_url=?, api_key=?,
					temperature=?, max_tokens=?, system_prompt=?,
					support_stream=?, support_think=?, is_default=?, status=?,
					updated_at=datetime('now')
				where id=?
				""",
                (
                    data["name"],
                    data["model_id"],
                    data["model_type"],
                    data["base_url"],
                    data["api_key"],
                    data["temperature"],
                    data["max_tokens"],
                    data.get("system_prompt", ""),
                    data["support_stream"],
                    data["support_think"],
                    data["is_default"],
                    data["status"],
                    model_id,
                ),
            )
        return True, None

    @staticmethod
    def delete_model(model_id: int):
        with get_connection() as conn:
            conn.execute("delete from ai_model_usage where model_id=?", (model_id,))
            conn.execute("delete from ai_models where id=?", (model_id,))
        return True, None

    @staticmethod
    def set_default(model_id: int):
        with get_connection() as conn:
            conn.execute("update ai_models set is_default=0")
            conn.execute("update ai_models set is_default=1 where id=?", (model_id,))
        return True, None

    @staticmethod
    def record_usage(model_id: int, prompt_tokens: int, completion_tokens: int):
        total = prompt_tokens + completion_tokens
        with get_connection() as conn:
            conn.execute(
                """
				insert into ai_model_usage(model_id, prompt_tokens, completion_tokens, total_tokens)
				values(?, ?, ?, ?)
				""",
                (model_id, prompt_tokens, completion_tokens, total),
            )

    @overload
    @staticmethod
    def usage_summary() -> list[sqlite3.Row]: ...
    @overload
    @staticmethod
    def usage_summary(model_id: int) -> dict[str, Any]: ...
    @staticmethod
    def usage_summary(
        model_id: int | None = None,
    ) -> list[sqlite3.Row] | dict[str, Any]:
        with get_connection() as conn:
            if model_id:
                row = conn.execute(
                    """
					select coalesce(sum(prompt_tokens), 0) prompt,
						coalesce(sum(completion_tokens), 0) completion,
						coalesce(sum(total_tokens), 0) total,
						count(*) calls
					from ai_model_usage where model_id=?
					""",
                    (model_id,),
                ).fetchone()
                return dict(
                    prompt=row["prompt"],
                    completion=row["completion"],
                    total=row["total"],
                    calls=row["calls"],
                )
            rows = conn.execute(
                """
				select m.id, m.name, m.model_id, m.is_default,
					coalesce(sum(u.prompt_tokens), 0) prompt,
					coalesce(sum(u.completion_tokens), 0) completion,
					coalesce(sum(u.total_tokens), 0) total,
					count(u.id) calls
				from ai_models m
				left join ai_model_usage u on u.model_id=m.id
				group by m.id
				order by m.is_default desc, total desc, m.id desc
				"""
            ).fetchall()
            return rows
