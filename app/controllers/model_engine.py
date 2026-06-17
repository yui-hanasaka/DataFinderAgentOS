import json
from typing import Any

from app.controllers.admin import AdminBaseHandler
from app.models.errors import log_error
from app.models.model_client import chat_complete, iter_sse_chunks, parse_chat_response
from app.models.model_engine import PER_PAGE, ModelRepository
from app.models.rate_limit import check_rate_limit


class AdminModelEngineHandler(AdminBaseHandler):
    def get(self) -> None:
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        models, total = ModelRepository.list_models(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_model = (
            ModelRepository.get_model_masked(int(edit_id))
            if edit_id.isdigit()
            else None
        )
        usage_rows = ModelRepository.usage_summary()
        totals = {
            "calls": sum(int(row["calls"]) for row in usage_rows),
            "total": sum(int(row["total"]) for row in usage_rows),
            "prompt": sum(int(row["prompt"]) for row in usage_rows),
            "completion": sum(int(row["completion"]) for row in usage_rows),
        }
        self.render(
            "admin/models.html",
            title="模型引擎",
            username=self.current_user,
            models=models,
            total=total,
            page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            edit_model=edit_model,
            usage_rows=usage_rows,
            totals=totals,
            msg=self._message(),
        )

    def post(self) -> None:
        action = self.get_body_argument("action", "")
        model_id = self.get_body_argument("id", "")
        if action == "delete" and model_id.isdigit():
            ok, msg = ModelRepository.delete_model(int(model_id))
            return self._redirect_with_message(
                "/admin/models", msg or "模型已删除" if ok else msg
            )
        if action == "set_default" and model_id.isdigit():
            ok, msg = ModelRepository.set_default(int(model_id))
            return self._redirect_with_message(
                "/admin/models", msg or "已设为默认模型" if ok else msg
            )

        data = {
            "name": self.get_body_argument("name", "").strip(),
            "model_id": self.get_body_argument("model_id_value", "").strip(),
            "model_type": self.get_body_argument("model_type", "text"),
            "base_url": self.get_body_argument("base_url", "").strip(),
            "api_key": self.get_body_argument("api_key", "").strip(),
            "temperature": float(self.get_body_argument("temperature", "0.7") or 0.7),
            "max_tokens": int(self.get_body_argument("max_tokens", "1024") or 1024),
            "system_prompt": self.get_body_argument("system_prompt", "").strip(),
            "support_stream": 1
            if self.get_body_argument("support_stream", "0") == "1"
            else 0,
            "support_think": 1
            if self.get_body_argument("support_think", "0") == "1"
            else 0,
            "is_default": 1 if self.get_body_argument("is_default", "0") == "1" else 0,
            "status": self.get_body_argument("status", "enabled"),
        }
        if model_id.isdigit():
            ok, msg = ModelRepository.update_model(int(model_id), data)
            return self._redirect_with_message(
                "/admin/models", msg or "模型已更新" if ok else msg
            )
        ok, msg = ModelRepository.create_model(data)
        self._redirect_with_message("/admin/models", msg or "模型已新增" if ok else msg)


class AdminModelTestHandler(AdminBaseHandler):
    def get(self, model_id: str) -> None:
        model = ModelRepository.get_model(int(model_id)) if model_id.isdigit() else None
        if not model:
            return self.redirect("/admin/models")
        usage = ModelRepository.usage_summary(model["id"])
        self.render(
            "admin/model_test.html",
            title=f"模型测试 · {model['name']}",
            username=self.current_user,
            model=model,
            usage=usage,
        )


class AdminModelChatHandler(AdminBaseHandler):
    async def post(self, model_id: str) -> None:
        if not check_rate_limit(f"admin_model_chat:{self.current_user}", 30, 60):
            self.set_status(429)
            return self.write({"error": "请求过于频繁，请稍后再试"})
        model = ModelRepository.get_model(int(model_id)) if model_id.isdigit() else None
        if not model:
            self.set_status(404)
            return self.write({"error": "模型不存在"})
        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            return self.write({"error": "请求体不是合法 JSON"})

        user_message = (payload.get("message") or "").strip()
        stream = bool(payload.get("stream"))
        think = bool(payload.get("think"))
        if not user_message:
            self.set_status(400)
            return self.write({"error": "请输入对话内容"})

        messages = []
        if model["system_prompt"]:
            messages.append({"role": "system", "content": model["system_prompt"]})
        if think:
            messages.append(
                {
                    "role": "system",
                    "content": "请按 <think>...</think> 输出推理过程后再给出答案。",
                }
            )
        messages.append({"role": "user", "content": user_message})

        try:
            if stream and model["support_stream"]:
                return await self._stream_response(model, messages)
            return await self._sync_response(model, messages)
        except Exception as e:
            log_error("AdminModelChatHandler", e)
            self.set_status(502)
            # If SSE headers haven't been sent yet, write JSON
            if "text/event-stream" not in self._headers.get("Content-Type", ""):
                self.write({"error": "模型调用失败，请稍后重试"})

    async def _sync_response(
        self, model: dict[str, Any], messages: list[dict[str, str]]
    ) -> None:
        model_id: int = int(model["id"])
        base_url: str = str(model["base_url"])
        api_key: str = str(model["api_key"])
        model_name: str = str(model["model_id"])
        temperature: float = float(model["temperature"])
        max_tokens: int = int(model["max_tokens"])
        resp = await chat_complete(
            base_url,
            api_key,
            model_name,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        raw = await resp.aread()
        parsed = parse_chat_response(raw)
        ModelRepository.record_usage(
            model_id,
            int(parsed["prompt_tokens"]),
            int(parsed["completion_tokens"]),
        )
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write(parsed)

    async def _stream_response(
        self, model: dict[str, Any], messages: list[dict[str, str]]
    ) -> None:
        model_id: int = int(model["id"])
        base_url: str = str(model["base_url"])
        api_key: str = str(model["api_key"])
        model_name: str = str(model["model_id"])
        temperature: float = float(model["temperature"])
        max_tokens: int = int(model["max_tokens"])
        self.set_header("Content-Type", "text/event-stream; charset=utf-8")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("X-Accel-Buffering", "no")
        prompt_tokens = 0
        completion_tokens = 0
        try:
            resp = await chat_complete(
                base_url,
                api_key,
                model_name,
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in iter_sse_chunks(resp):
                usage = chunk.get("usage") or {}
                if usage:
                    prompt_tokens = max(
                        prompt_tokens, int(usage.get("prompt_tokens") or 0)
                    )
                    completion_tokens = max(
                        completion_tokens, int(usage.get("completion_tokens") or 0)
                    )
                delta = ((chunk.get("choices") or [{}])[0]).get("delta") or {}
                text = delta.get("content") or ""
                reasoning = delta.get("reasoning_content") or ""
                try:
                    self.write(
                        "data: "
                        + json.dumps({"content": text, "reasoning": reasoning})
                        + "\n\n"
                    )
                    await self.flush()
                except Exception:
                    break
            ModelRepository.record_usage(model_id, prompt_tokens, completion_tokens)
        except Exception as e:
            log_error("AdminModelChatHandler SSE stream", e)
            self.write(
                "data: " + json.dumps({"error": "模型调用失败，请稍后重试"}) + "\n\n"
            )
        self.write("data: [DONE]\n\n")
        await self.flush()
