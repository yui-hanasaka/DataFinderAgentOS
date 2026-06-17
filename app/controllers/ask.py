import json

from app.controllers.base import BaseHandler
from app.models.errors import log_error
from app.models.rate_limit import check_rate_limit
from app.models.model_client import chat_complete, parse_chat_response
from app.models.model_engine import ModelRepository
from app.models.warehouse import WarehouseRepository


class AskBaseHandler(BaseHandler):
    def get_current_user(self):
        raw = self.get_secure_cookie("username")
        return raw.decode("utf-8") if raw else None

    def prepare(self):
        if not self.current_user:
            return self.redirect("/user/login")


class AskHomeHandler(AskBaseHandler):
    def get(self):
        self.render(
            "web/ask.html",
            title="问数",
            username=self.current_user,
            query="",
            results=[],
            columns=[],
            ask_init_json=json.dumps({"columns": [], "results": []}),
            error=None,
        )


# Public tables accessible via AI ask — only collected/warehouse data
# Schema hint exposed to AI model — only public non-sensitive tables
_PUBLIC_TABLES = {
    "watchtower_items": [
        "id",
        "source_id",
        "title",
        "content",
        "url",
        "sentiment",
        "risk",
        "published_at",
        "collected_at",
        "is_deep_collected",
        "deep_collected_at",
        "deep_task_id",
        "summary",
        "keywords",
        "created_at",
    ],
    "watchtower_sources": [
        "id",
        "name",
        "source_type",
        "url",
        "fetch_interval",
        "status",
        "last_fetched",
        "created_at",
    ],
    "deep_contents": [
        "id",
        "item_id",
        "task_id",
        "title",
        "url",
        "summary",
        "keywords",
        "sentiment",
        "risk",
        "created_at",
    ],
    "digital_employees": [
        "id",
        "name",
        "avatar",
        "status",
        "created_at",
    ],
    "skills": [
        "id",
        "code",
        "name",
        "skill_type",
        "status",
    ],
}


class AskQueryHandler(AskBaseHandler):
    def _public_schema_hint(self):
        hints = []
        for table, cols in _PUBLIC_TABLES.items():
            hints.append(f"{table}({', '.join(cols)})")
        return "; ".join(hints)

    async def post(self):
        key = f"ask_query:ip:{self.request.remote_ip}"
        if not check_rate_limit(key, 20, 60):
            self.set_status(429)
            return self.write({"ok": False, "error": "请求过于频繁，请稍后再试"})

        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            return self.write({"ok": False, "error": "请求格式错误"})

        nl_query = (payload.get("query") or "").strip()
        if not nl_query:
            return self.write({"ok": False, "error": "请输入查询内容"})
        if len(nl_query) > 500:
            return self.write({"ok": False, "error": "查询内容过长"})

        model_row = ModelRepository.get_default_model()
        if not model_row:
            return self.write({"ok": False, "error": "未配置默认模型"})

        schema = self._public_schema_hint()
        prompt = (
            f"数据库表结构（只读，只能查询以下表）：{schema}\n\n"
            f"请将以下自然语言转换为 SQLite SELECT 语句，只返回 SQL，不要解释：\n{nl_query}"
        )
        sql = ""
        try:
            resp = await chat_complete(
                model_row["base_url"],
                model_row["api_key"],
                model_row["model_id"],
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=512,
                stream=False,
            )
            raw = await resp.aread()
            parsed = parse_chat_response(raw)
            sql = parsed.get("content", "").strip()
            # Strip markdown code fences if present
            if sql.startswith("```"):
                sql = sql.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        except Exception as e:
            log_error("AskQueryHandler model call", e)
            return self.write({"ok": False, "error": "模型调用失败，请稍后重试"})

        rows, cols, err = WarehouseRepository.execute_query(sql)
        if err:
            log_error("AskQueryHandler SQL execution", Exception(str(err)[:200]))
            return self.write({"ok": False, "error": "查询无法执行，请调整问题"})

        # Convert rows to list of dicts
        dict_rows: list[dict[str, object]] = []
        if rows and cols:
            for r in rows:
                d: dict[str, object] = {}
                for c in cols:
                    val = r[c] if c in r.keys() else None
                    d[c] = val
                dict_rows.append(d)

        # Store in ask_history (SQL kept server-side only)
        try:
            from app.models.db import get_connection

            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO ask_history(user_id, query, generated_sql, result_count, status, model_id)
                       VALUES((SELECT id FROM users WHERE username=?), ?, ?, ?, 'ok', ?)""",
                    (self.current_user, nl_query, sql, len(dict_rows), model_row["id"]),
                )
        except Exception as e:
            log_error("AskQueryHandler ask_history", e)

        self.set_header("Content-Type", "application/json")
        self.write({"ok": True, "columns": cols, "rows": dict_rows})
