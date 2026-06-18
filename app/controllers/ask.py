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
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.set_header("Pragma", "no-cache")
        self.set_header("Expires", "0")
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
                {
                    "ok": False,
                    "error": "模型 API Key 未设置或已失效，请联系管理员更新模型配置",
                }
            )

        # SSE streaming Agentic query
        self.set_header("Content-Type", "text/event-stream; charset=utf-8")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("X-Accel-Buffering", "no")

        from app.agents.agent_loop import run as agent_run

        system_prompt = (
            "你是数据分析助手，必须通过 warehouse_query 工具查询数据库来回答用户问题。\n"
            "\n"
            "【强制规则 — 违反将导致错误】\n"
            "1. 你必须调用 warehouse_query 工具执行查询，不允许在没有查询数据的情况下做任何回答。\n"
            "2. 如果查询失败或返回空结果，你必须分析原因、修正查询、重试，直到成功拿到数据。\n"
            '3. 你绝对不能：在没有调用工具的情况下直接总结、推测、分析、或告诉用户"没有数据"。\n'
            "4. 你绝对不能：先输出文字再调用工具——必须先调用工具，拿到结果后再说话。\n"
            "5. 查询成功后，用 1-2 句简短中文总结数据含义即可，不要展开分析、不要给建议、不要延伸讨论。\n"
            "6. 不要输出表格数据本身——表格会由系统自动渲染。你只需简短总结+标注数据条数。\n"
            "\n"
            "【正确工作流程】\n"
            '第一步：调用 warehouse_query(question="用户的自然语言查询") → 等待结果\n'
            "第二步：如果出错，修正查询重试 → 直到成功\n"
            '第三步：成功后简短总结（1-2句），例如："查询完成，共返回 15 条数据。其中 xxx 类别占比最高…"\n'
            "\n"
            "记住：没有 warehouse_query 的调用 = 错误的回答。永远先查询，再说话。"
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
                if (
                    event_type == "tool_result"
                    and data.get("name") == "warehouse_query"
                ):
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
