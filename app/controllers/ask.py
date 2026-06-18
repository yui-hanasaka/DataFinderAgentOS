import json

from app.controllers.base import BaseHandler
from app.models.errors import log_error
from app.models.rate_limit import check_rate_limit
from app.models.model_engine import ModelRepository


class AskBaseHandler(BaseHandler):
    def get_current_user(self) -> str | None:
        raw = self.get_secure_cookie("username")
        return raw.decode("utf-8") if raw else None

    def prepare(self) -> None:
        if not self.current_user:
            return self.redirect("/user/login")


class AskHomeHandler(AskBaseHandler):
    def get(self) -> None:
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


class AskQueryHandler(AskBaseHandler):
    async def post(self) -> None:
        key = f"ask_query:ip:{self.request.remote_ip}"
        if not check_rate_limit(key, 20, 60):
            self.set_status(429)
            self.set_header("Content-Type", "application/json")
            return self.write({"ok": False, "error": "请求过于频繁，请稍后再试"})

        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_header("Content-Type", "application/json")
            return self.write({"ok": False, "error": "请求格式错误"})

        nl_query = (payload.get("query") or "").strip()
        if not nl_query:
            self.set_header("Content-Type", "application/json")
            return self.write({"ok": False, "error": "请输入查询内容"})
        if len(nl_query) > 500:
            self.set_header("Content-Type", "application/json")
            return self.write({"ok": False, "error": "查询内容过长"})

        model_row = ModelRepository.get_default_model()
        if not model_row:
            self.set_header("Content-Type", "application/json")
            return self.write({"ok": False, "error": "未配置默认模型"})
        if not model_row.get("api_key"):
            self.set_header("Content-Type", "application/json")
            return self.write(
                {"ok": False, "error": "模型 API Key 未设置或已失效，请联系管理员更新模型配置"}
            )

        # SSE streaming Agentic query
        self.set_header("Content-Type", "text/event-stream; charset=utf-8")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("X-Accel-Buffering", "no")

        from app.agents.agent_loop import run as agent_run

        system_prompt = (
            "你是数据分析助手。使用 warehouse_query 工具查询数据库，"
            "然后以清晰的中文总结查询结果。如果查询出错，分析错误原因并重试。"
        )

        messages: list[dict[str, object]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": nl_query},
        ]

        # Accumulate the final tool result for table/chart rendering
        final_columns: list[str] = []
        final_rows: list[dict[str, object]] = []

        async def _sse(event_type: str, data: object) -> None:
            nonlocal final_columns, final_rows
            if event_type == "text":
                self.write(
                    f"data: {json.dumps({'type': 'text', 'content': str(data)})}\n\n"
                )
            elif isinstance(data, dict):
                payload = json.dumps({"type": event_type, **data})
                self.write(f"data: {payload}\n\n")
                # Extract columns/rows from warehouse_query tool result
                if event_type == "tool_result" and data.get("name") == "warehouse_query":
                    try:
                        result_data = json.loads(str(data.get("content", "[]")))
                        if isinstance(result_data, list) and len(result_data) > 0:
                            first = result_data[0]
                            if isinstance(first, dict):
                                final_columns = list(first.keys())
                                final_rows = result_data
                    except (json.JSONDecodeError, Exception):
                        pass
            else:
                self.write(
                    f"data: {json.dumps({'type': event_type, 'data': str(data)})}\n\n"
                )
            try:
                await self.flush()
            except Exception:
                pass

        try:
            await agent_run(
                nl_query,
                messages,
                model_row,
                _sse,
                allowed_tools=["warehouse_query"],
            )
        except Exception as e:
            log_error("AskQueryHandler agent_run", e)
            self.write(
                f"data: {json.dumps({'type': 'error', 'message': f'查询执行失败: {e}'})}\n\n"
            )
            await self.flush()

        # Send final result with columns/rows for table + chart
        self.write(
            f"data: {json.dumps({'type': 'done', 'columns': final_columns, 'rows': final_rows})}\n\n"
        )
        self.write("data: [DONE]\n\n")
        await self.flush()
