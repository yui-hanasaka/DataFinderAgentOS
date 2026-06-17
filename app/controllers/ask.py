import json

from app.controllers.base import BaseHandler
from app.models.db import get_connection
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
            error=None,
        )


class AskQueryHandler(AskBaseHandler):
    def check_xsrf_cookie(self):
        pass

    def _schema_hint(self):
        with get_connection() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        hints = []
        with get_connection() as conn:
            for t in tables:
                cols = conn.execute(f"PRAGMA table_info({t['name']})").fetchall()
                col_names = ", ".join(c["name"] for c in cols)
                hints.append(f"{t['name']}({col_names})")
        return "; ".join(hints)

    async def post(self):
        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            return self.write({"error": "请求格式错误"})

        nl_query = (payload.get("query") or "").strip()
        if not nl_query:
            return self.write({"error": "请输入查询内容"})

        model_row = ModelRepository.get_default_model()
        if not model_row:
            return self.write({"error": "未配置默认模型"})

        schema = self._schema_hint()
        prompt = (
            f"数据库表结构：{schema}\n\n"
            f"请将以下自然语言转换为 SQLite SELECT 语句，只返回 SQL，不要解释：\n{nl_query}"
        )
        try:
            resp = chat_complete(
                model_row["base_url"],
                model_row["api_key"],
                model_row["model_id"],
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=512,
                stream=False,
            )
            parsed = parse_chat_response(resp.read())
            sql = parsed.get("content", "").strip()
            # Strip markdown code fences if present
            if sql.startswith("```"):
                sql = sql.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        except Exception as e:
            return self.write({"error": f"模型调用失败：{e}"})

        rows, cols, err = WarehouseRepository.execute_query(sql)
        if err:
            return self.write({"error": f"SQL执行失败：{err}", "sql": sql})
        self.set_header("Content-Type", "application/json")
        self.write(
            {"columns": cols, "rows": [list(r) for r in (rows or [])], "sql": sql}
        )
