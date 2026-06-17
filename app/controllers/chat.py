import json

from app.controllers.base import BaseHandler
from app.models.chat import ChatRepository
from app.models.db import get_connection
from app.models.employee import EmployeeRepository
from app.models.model_client import chat_complete, iter_sse_chunks
from app.models.model_engine import ModelRepository
from app.models.skill_dispatcher import dispatch


class ChatBaseHandler(BaseHandler):
    def get_current_user(self):
        raw = self.get_secure_cookie("username")
        return raw.decode("utf-8") if raw else None

    def prepare(self):
        if not self.current_user:
            return self.redirect("/user/login")

    def _user_id(self):
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username=?", (self.current_user,)
            ).fetchone()
        return row["id"] if row else 0


class ChatHomeHandler(ChatBaseHandler):
    def get(self):
        user_id = self._user_id()
        sessions, _ = ChatRepository.list_sessions(user_id, page=1)
        employees = EmployeeRepository.list_all_active()
        self.render(
            "web/chat.html",
            title="对话",
            username=self.current_user,
            sessions=sessions,
            current_session=None,
            messages=[],
            employees=employees,
            current_employee_id=0,
        )


class ChatSessionHandler(ChatBaseHandler):
    def get(self, session_id):
        user_id = self._user_id()
        session = ChatRepository.get_session(int(session_id))
        if not session or session["user_id"] != user_id:
            return self.redirect("/chat")
        sessions, _ = ChatRepository.list_sessions(user_id, page=1)
        messages = ChatRepository.list_messages(int(session_id))
        employees = EmployeeRepository.list_all_active()
        self.render(
            "web/chat.html",
            title=session["title"],
            username=self.current_user,
            sessions=sessions,
            current_session=session,
            messages=messages,
            employees=employees,
            current_employee_id=session["employee_id"],
        )


class ChatNewHandler(ChatBaseHandler):
    def get(self):
        user_id = self._user_id()
        employee_id = int(self.get_query_argument("employee_id", "0") or 0)
        sess_id, _ = ChatRepository.create_session(user_id, employee_id, "新对话")
        self.redirect(f"/chat/session/{sess_id}")

    def post(self):
        user_id = self._user_id()
        employee_id = int(self.get_body_argument("employee_id", "0") or 0)
        sess_id, _ = ChatRepository.create_session(user_id, employee_id, "新对话")
        self.redirect(f"/chat/session/{sess_id}")


class ChatDeleteHandler(ChatBaseHandler):
    def post(self, session_id):
        user_id = self._user_id()
        session = ChatRepository.get_session(int(session_id))
        if session and session["user_id"] == user_id:
            ChatRepository.delete_session(int(session_id))
        self.redirect("/chat")


class ChatBatchDeleteHandler(ChatBaseHandler):
    def post(self):
        user_id = self._user_id()
        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            return self.write({"error": "请求体格式错误"})
        ids = payload.get("ids") or []
        if not isinstance(ids, list) or not ids:
            self.set_status(400)
            return self.write({"error": "请选择要删除的对话"})
        count = ChatRepository.delete_sessions([int(i) for i in ids], user_id)
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write({"ok": True, "count": count})


class ChatSendHandler(ChatBaseHandler):
    def check_xsrf_cookie(self):
        pass

    def _get_api_keys(self):
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT api_type, api_key FROM api_keys WHERE status='enabled'"
            ).fetchall()
        return {r["api_type"]: r["api_key"] for r in rows}

    async def post(self, session_id):
        user_id = self._user_id()
        session = ChatRepository.get_session(int(session_id))
        if not session or session["user_id"] != user_id:
            self.set_status(403)
            return self.write({"error": "无权限"})
        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            return self.write({"error": "请求体格式错误"})

        user_text = (payload.get("message") or "").strip()
        if not user_text:
            self.set_status(400)
            return self.write({"error": "消息不能为空"})

        ChatRepository.add_message(int(session_id), "user", user_text)

        # Auto-title from first message
        if not session["title"] or session["title"] == "新对话":
            ChatRepository.update_session_title(int(session_id), user_text[:20])

        dispatched = dispatch(user_text, self._get_api_keys())

        # Non-AI skill response (weather direct answer, music placeholder)
        if dispatched["type"] == "skill" and dispatched["skill_code"] in (
            "weather",
            "music",
        ):
            reply = dispatched["processed_content"]
            ChatRepository.add_message(
                int(session_id),
                "assistant",
                reply,
                skill_meta=json.dumps(dispatched["skill_meta"]),
            )
            self.set_header("Content-Type", "text/event-stream; charset=utf-8")
            self.set_header("Cache-Control", "no-cache")
            self.write(f"data: {json.dumps({'content': reply})}\n\n")
            self.write("data: [DONE]\n\n")
            return await self.flush()

        # AI-routed: build messages list
        employee = None
        if session["employee_id"]:
            employee = EmployeeRepository.get_employee(session["employee_id"])
        model_row = None
        if employee and employee["model_id"]:
            model_row = ModelRepository.get_model(employee["model_id"])
        if not model_row:
            model_row = ModelRepository.get_default_model()
        if not model_row:
            ChatRepository.add_message(
                int(session_id), "assistant", "未配置可用模型，请联系管理员。"
            )
            self.set_header("Content-Type", "text/event-stream; charset=utf-8")
            self.set_header("Cache-Control", "no-cache")
            self.write('data: {"content":"未配置可用模型，请联系管理员。"}\n\n')
            self.write("data: [DONE]\n\n")
            return await self.flush()

        messages = []
        system_prompt = dispatched["skill_meta"].get("system_override") or (
            employee["system_prompt"] if employee else model_row["system_prompt"]
        )
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        # Inject search results if websearch skill
        search_inject = dispatched["skill_meta"].get("inject_prompt")
        content = search_inject if search_inject else dispatched["processed_content"]

        history = ChatRepository.list_messages(int(session_id))
        for m in history[-20:]:
            if m["role"] in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m["content"]})
        # Replace last user entry with dispatched content
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"] = content
        else:
            messages.append({"role": "user", "content": content})

        self.set_header("Content-Type", "text/event-stream; charset=utf-8")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("X-Accel-Buffering", "no")

        full_reply = []
        try:
            resp = chat_complete(
                model_row["base_url"],
                model_row["api_key"],
                model_row["model_id"],
                messages,
                temperature=model_row["temperature"],
                max_tokens=model_row["max_tokens"],
                stream=True,
            )
            prompt_tokens = completion_tokens = 0
            for chunk in iter_sse_chunks(resp):
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
                if text:
                    full_reply.append(text)
                    self.write(f"data: {json.dumps({'content': text})}\n\n")
                    await self.flush()
            ModelRepository.record_usage(
                model_row["id"], prompt_tokens, completion_tokens
            )
        except Exception as ex:
            err_msg = f"模型调用失败：{ex}"
            full_reply.append(err_msg)
            self.write(f"data: {json.dumps({'content': err_msg})}\n\n")

        ChatRepository.add_message(
            int(session_id),
            "assistant",
            "".join(full_reply),
            skill_meta=json.dumps(dispatched["skill_meta"])
            if dispatched["skill_meta"]
            else None,
        )
        self.write("data: [DONE]\n\n")
        await self.flush()


class ChatExportHandler(ChatBaseHandler):
    def get(self, session_id):
        user_id = self._user_id()
        session = ChatRepository.get_session(int(session_id))
        if not session or session["user_id"] != user_id:
            return self.redirect("/chat")
        messages = ChatRepository.list_messages(int(session_id))

        import os
        from io import BytesIO

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        # Try to register Chinese font if available
        font_name = "Helvetica"
        font_paths = [
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\msyh.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    pdfmetrics.registerFont(TTFont("CJK", fp))
                    font_name = "CJK"
                except Exception:
                    pass
                break

        from reportlab.lib.colors import HexColor

        title_style = ParagraphStyle(
            "t", fontName=font_name, fontSize=16, spaceAfter=12
        )
        user_style = ParagraphStyle(
            "u",
            fontName=font_name,
            fontSize=10,
            textColor=HexColor("#1a73e8"),
            spaceAfter=4,
        )
        asst_style = ParagraphStyle(
            "a",
            fontName=font_name,
            fontSize=10,
            textColor=HexColor("#333333"),
            spaceAfter=8,
        )

        story = [Paragraph(session["title"], title_style), Spacer(1, 0.3 * cm)]
        for m in messages:
            label = "用户：" if m["role"] == "user" else "助手："
            style = user_style if m["role"] == "user" else asst_style
            text = (
                (label + m["content"])
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(text, style))
        doc.build(story)

        pdf_bytes = buf.getvalue()
        self.set_header("Content-Type", "application/pdf")
        filename = f"conversation_{session_id}.pdf"
        self.set_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.write(pdf_bytes)
