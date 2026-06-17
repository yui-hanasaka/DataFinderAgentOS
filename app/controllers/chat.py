import asyncio
import json
from typing import Any

import httpx
from loguru import logger
from tornado.iostream import StreamClosedError

from app.agents import agent_loop
from app.controllers.base import BaseHandler
from app.models.chat import ChatRepository
from app.models.db import get_connection
from app.models.employee import EmployeeRepository
from app.models.errors import log_error
from app.models.model_engine import ModelRepository
from app.models.rate_limit import check_rate_limit
from app.models.skill_dispatcher import dispatch
from app.models.validators import parse_int


class ChatBaseHandler(BaseHandler):
    def get_current_user(self) -> str | None:
        raw = self.get_secure_cookie("username")
        return raw.decode("utf-8") if raw else None

    def prepare(self) -> None:
        if not self.current_user:
            return self.redirect("/user/login")

    def _user_id(self) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username=?", (self.current_user,)
            ).fetchone()
        return row["id"] if row else 0


class ChatHomeHandler(ChatBaseHandler):
    def get(self) -> None:
        user_id = self._user_id()
        sessions, _ = ChatRepository.list_sessions(user_id, page=1)
        employees = EmployeeRepository.list_all_active()
        enabled_models = ModelRepository.list_all_enabled()
        models_for_template = [
            {"id": r["id"], "name": r["name"], "model_type": r["model_type"]}
            for r in enabled_models
        ]
        self.render(
            "web/chat.html",
            title="对话",
            username=self.current_user,
            sessions=sessions,
            current_session=None,
            messages=[],
            employees=employees,
            current_employee_id=0,
            models=models_for_template,
            current_model_id=0,
            current_model_name="跟随员工",
            is_model_custom=False,
        )


class ChatSessionHandler(ChatBaseHandler):
    def get(self, session_id: str) -> None:
        user_id = self._user_id()
        session = ChatRepository.get_session(int(session_id))
        if not session or session["user_id"] != user_id:
            return self.redirect("/chat")
        sessions, _ = ChatRepository.list_sessions(user_id, page=1)
        messages = ChatRepository.list_messages(int(session_id))
        employees = EmployeeRepository.list_all_active()
        enabled_models = ModelRepository.list_all_enabled()
        models_for_template = [
            {"id": r["id"], "name": r["name"], "model_type": r["model_type"]}
            for r in enabled_models
        ]
        sess_model_id = int(session["model_id"] or 0)
        if sess_model_id > 0:
            model_row = ModelRepository.get_model_masked(sess_model_id)
            current_model_name = model_row["name"] if model_row else "未知模型"
            is_model_custom = True
        else:
            current_model_name = "跟随员工"
            is_model_custom = False

        self.render(
            "web/chat.html",
            title=session["title"],
            username=self.current_user,
            sessions=sessions,
            current_session=session,
            messages=messages,
            employees=employees,
            current_employee_id=session["employee_id"],
            models=models_for_template,
            current_model_id=sess_model_id,
            current_model_name=current_model_name,
            is_model_custom=is_model_custom,
        )


class ChatNewHandler(ChatBaseHandler):
    def get(self) -> None:
        user_id = self._user_id()
        employee_id = parse_int(self.get_query_argument("employee_id", "0"), 0)
        sess_id, _ = ChatRepository.create_session(user_id, employee_id, "新对话")
        self.redirect(f"/chat/session/{sess_id}")

    def post(self) -> None:
        user_id = self._user_id()
        if not check_rate_limit(f"chat_new:user:{user_id}", 10, 60):
            self.set_status(429)
            self.write("请求过于频繁，请稍后再试")
            return
        employee_id = parse_int(self.get_body_argument("employee_id", "0"), 0)
        sess_id, _ = ChatRepository.create_session(user_id, employee_id, "新对话")
        self.redirect(f"/chat/session/{sess_id}")


class ChatDeleteHandler(ChatBaseHandler):
    def post(self, session_id: str) -> None:
        user_id = self._user_id()
        if not check_rate_limit(f"chat_delete:user:{user_id}", 5, 60):
            self.set_status(429)
            self.write("请求过于频繁，请稍后再试")
            return
        session = ChatRepository.get_session(int(session_id))
        if session and session["user_id"] == user_id:
            ChatRepository.delete_session(int(session_id))
        self.redirect("/chat")


class ChatBatchDeleteHandler(ChatBaseHandler):
    def post(self) -> None:
        user_id = self._user_id()
        if not check_rate_limit(f"chat_batch_delete:user:{user_id}", 5, 60):
            self.set_status(429)
            self.set_header("Content-Type", "application/json; charset=utf-8")
            return self.write({"error": "请求过于频繁，请稍后再试"})
        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            return self.write({"error": "请求体格式错误"})
        ids = payload.get("ids") or []
        if not isinstance(ids, list) or not ids:
            self.set_status(400)
            return self.write({"error": "请选择要删除的对话"})
        numeric_ids = [int(i) for i in ids if str(i).isdigit()]
        if not numeric_ids:
            self.set_status(400)
            return self.write({"error": "请选择有效的对话"})
        count = ChatRepository.delete_sessions(numeric_ids, user_id)
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write({"ok": True, "count": count})


class ChatEmployeeHandler(ChatBaseHandler):
    def post(self) -> None:
        user_id = self._user_id()
        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            return self.write({"error": "请求体格式错误"})
        session_id = parse_int(payload.get("session_id"), 0)
        employee_id = parse_int(payload.get("employee_id"), 0)
        if not session_id or not employee_id:
            self.set_status(400)
            return self.write({"error": "参数不完整"})
        session = ChatRepository.get_session(session_id)
        if not session or session["user_id"] != user_id:
            self.set_status(403)
            return self.write({"error": "无权限"})
        ChatRepository.update_session_employee(session_id, employee_id)
        logger.info(
            "用户 {} 切换员工 — 会话#{} → employee_id={} (已重置模型覆盖)",
            self.current_user,
            session_id,
            employee_id,
        )
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write({"ok": True})


class ChatModelHandler(ChatBaseHandler):
    def post(self) -> None:
        user_id = self._user_id()
        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            return self.write({"error": "请求体格式错误"})
        session_id = parse_int(payload.get("session_id"), 0)
        model_id = parse_int(payload.get("model_id"), 0)
        if not session_id:
            self.set_status(400)
            return self.write({"error": "参数不完整"})
        session = ChatRepository.get_session(session_id)
        if not session or session["user_id"] != user_id:
            self.set_status(403)
            return self.write({"error": "无权限"})
        # Verify model exists if not resetting to 0
        model_name = "跟随员工"
        if model_id > 0:
            model_row = ModelRepository.get_model(model_id)
            if not model_row or model_row.get("status") != "enabled":
                self.set_status(404)
                return self.write({"error": "模型不可用"})
            model_name = model_row["name"]
        ChatRepository.update_session_model(session_id, model_id)
        logger.info(
            "用户 {} 切换模型 — 会话#{} → model_id={} ({})",
            self.current_user,
            session_id,
            model_id,
            model_name,
        )
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write({"ok": True, "model_id": model_id, "model_name": model_name})


class ChatSendHandler(ChatBaseHandler):
    def _get_api_keys(self) -> dict[str, str]:
        from app.models.secrets_store import decrypt

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT api_type, api_key FROM api_keys WHERE status='enabled'"
            ).fetchall()
        return {r["api_type"]: decrypt(r["api_key"]) for r in rows}

    async def post(self, session_id: str) -> None:
        user_id = self._user_id()
        key = f"chat_send:user:{user_id}"
        if not check_rate_limit(key, 30, 60):
            logger.warning("用户 {} 发送消息频率超限", self.current_user)
            self.set_status(429)
            return self.write({"error": "请求过于频繁，请稍后再试"})

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
        if len(user_text) > 10000:
            self.set_status(400)
            return self.write({"error": "消息过长，最多支持 10000 个字符"})

        ChatRepository.add_message(int(session_id), "user", user_text)

        # Auto-title from first message
        if not session["title"] or session["title"] == "新对话":
            title = user_text[:50]
            if len(user_text) > 50:
                title += "..."
            ChatRepository.update_session_title(int(session_id), title)

        try:
            dispatched = await dispatch(user_text, self._get_api_keys())
        except Exception as e:
            log_error("ChatSendHandler dispatch", e)
            self.set_status(500)
            self.set_header("Content-Type", "application/json; charset=utf-8")
            self.write({"error": "消息处理失败，请稍后重试"})
            return

        # Non-AI skill response (weather direct answer, music placeholder)
        if dispatched["type"] == "skill" and dispatched["skill_code"] == "weather":
            reply = dispatched["processed_content"]
            ChatRepository.add_message(
                int(session_id),
                "assistant",
                reply,
                skill_meta=json.dumps(dispatched["skill_meta"]),
            )
            self.set_header("Content-Type", "text/event-stream; charset=utf-8")
            self.set_header("Cache-Control", "no-cache")
            self.write(f"data: {json.dumps({'type': 'text', 'content': reply})}\n\n")
            self.write("data: [DONE]\n\n")
            return await self.flush()

        if dispatched["type"] == "skill" and dispatched["skill_code"] == "music":
            reply = dispatched["processed_content"]
            ChatRepository.add_message(
                int(session_id),
                "assistant",
                reply,
                skill_meta=json.dumps(dispatched["skill_meta"]),
            )
            self.set_header("Content-Type", "text/event-stream; charset=utf-8")
            self.set_header("Cache-Control", "no-cache")
            self.write(f"data: {json.dumps({'type': 'music_html', 'html': reply})}\n\n")
            self.write("data: [DONE]\n\n")
            return await self.flush()

        # AI-routed: build messages list
        # Always query employee (for persona/system_prompt)
        employee = None
        if session["employee_id"]:
            employee = EmployeeRepository.get_employee(session["employee_id"])

        # Model 3-tier fallback: session override > employee binding > default
        model_row = None
        if session["model_id"]:
            model_row = ModelRepository.get_model(session["model_id"])
        if not model_row and employee and employee["model_id"]:
            model_row = ModelRepository.get_model(employee["model_id"])
        if not model_row:
            model_row = ModelRepository.get_default_model()
        logger.info(
            "用户 {} 发送消息 — 会话#{} 模型: {} (覆盖={})",
            self.current_user,
            session_id,
            model_row["name"] if model_row else "无",
            bool(session["model_id"]),
        )
        if not model_row:
            ChatRepository.add_message(
                int(session_id), "assistant", "未配置可用模型，请联系管理员。"
            )
            self.set_header("Content-Type", "text/event-stream; charset=utf-8")
            self.set_header("Cache-Control", "no-cache")
            self.write('data: {"content":"未配置可用模型，请联系管理员。"}\n\n')
            self.write("data: [DONE]\n\n")
            return await self.flush()

        if not model_row.get("api_key"):
            ChatRepository.add_message(
                int(session_id),
                "assistant",
                "模型 API Key 未设置或已失效（服务器重启后加密密钥可能变更）。请联系管理员更新模型配置。",
            )
            self.set_header("Content-Type", "text/event-stream; charset=utf-8")
            self.set_header("Cache-Control", "no-cache")
            self.write(
                'data: {"content":"模型 API Key 未设置或已失效（服务器重启后加密密钥可能变更）。请联系管理员更新模型配置。"}\n\n'
            )
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
        # Fall back to original user_text if dispatched content is empty
        # (e.g. @西师妹 without trailing question)
        if not content.strip():
            content = user_text

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

        full_reply_list: list[str] = []

        async def _sse(event_type: str, data: Any) -> None:
            if event_type == "text":
                payload = json.dumps({"type": "text", "content": str(data)})
                full_reply_list.append(str(data))
            elif isinstance(data, dict):
                payload = json.dumps({"type": event_type, **data})
            else:
                payload = json.dumps({"type": event_type, "data": str(data)})
            try:
                self.write(f"data: {payload}\n\n")
                await self.flush()
            except StreamClosedError:
                raise
            except Exception:
                pass

        try:
            await agent_loop.run(user_text, messages, model_row, _sse)
        except StreamClosedError:
            logger.debug("Client disconnected during SSE streaming")
            return
        except Exception as e:
            log_error("ChatSendHandler agent_loop", e)
            err_msg = "模型调用失败，请稍后重试"
            full_reply_list.append(err_msg)
            self.write(f"data: {json.dumps({'type': 'text', 'content': err_msg})}\n\n")
            await self.flush()

        ChatRepository.add_message(
            int(session_id),
            "assistant",
            "".join(full_reply_list),
            skill_meta=json.dumps(dispatched["skill_meta"])
            if dispatched["skill_meta"]
            else None,
        )
        self.write("data: [DONE]\n\n")
        await self.flush()


class ChatExportHandler(ChatBaseHandler):
    def get(self, session_id: str) -> None:
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
            r"C:\Windows\Fonts\msyhbd.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "/usr/share/fonts/truetype/arphic/uming.ttc",
            "app/static/fonts/NotoSansSC-Regular.ttf",
        ]
        cjk_registered = False
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    pdfmetrics.registerFont(TTFont("CJK", fp))
                    font_name = "CJK"
                    cjk_registered = True
                    break
                except Exception as e:
                    log_error("ChatExportHandler font registration", e)
        if not cjk_registered:
            log_error(
                "ChatExportHandler: no CJK font found",
                FileNotFoundError(
                    "Chinese PDF export may produce tofu characters. "
                    "Checked paths: " + ", ".join(font_paths)
                ),
            )

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


class MusicSearchHandler(ChatBaseHandler):
    """Server-side music search aggregator.

    Queries all configured external music APIs plus built-in free sources
    in parallel, then returns aggregated results as JSON.
    """

    _MUSIC_API_TYPES = ("music", "music_qq", "music_netease")

    async def post(self) -> None:
        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            self.set_status(400)
            self.set_header("Content-Type", "application/json; charset=utf-8")
            self.write({"error": "请求体格式错误"})
            return

        query = (payload.get("q") or "").strip()
        if not query or len(query) > 200:
            self.set_status(400)
            self.set_header("Content-Type", "application/json; charset=utf-8")
            self.write({"error": "请输入有效的搜索关键词（1-200字符）"})
            return

        # Gather configured external API keys
        external_keys = self._get_music_api_keys()

        # Query external and built-in sources in parallel
        sources: list[dict[str, object]] = []

        # External API calls
        for key_info in external_keys:
            result = await self._query_external(query, key_info)
            if result:
                sources.append(result)

        # Built-in free sources (run in parallel)
        builtin_tasks = [
            self._query_itunes(query),
            self._query_musicbrainz(query),
            self._query_duckduckgo_music(query),
        ]
        builtin_results = await asyncio.gather(*builtin_tasks, return_exceptions=True)
        for r in builtin_results:
            if isinstance(r, dict) and r.get("items"):
                sources.append(r)

        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write({"sources": sources, "query": query})

    def _get_music_api_keys(self) -> list[dict[str, str]]:
        """Return list of enabled music API key configs with decrypted keys."""
        from app.models.secrets_store import decrypt

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT name, api_type, endpoint, api_key, config_json"
                " FROM api_keys"
                " WHERE api_type IN (?,?,?) AND status='enabled'",
                self._MUSIC_API_TYPES,
            ).fetchall()

        keys: list[dict[str, str]] = []
        for row in rows:
            raw = decrypt(row["api_key"])
            if raw:
                keys.append(
                    {
                        "name": row["name"],
                        "api_type": row["api_type"],
                        "endpoint": (row["endpoint"] or "").strip(),
                        "api_key": raw,
                        "config_json": row["config_json"] or "{}",
                    }
                )
        return keys

    # ── External API adapters ──────────────────────────────────────

    async def _query_external(
        self, query: str, key_info: dict[str, str]
    ) -> dict[str, object] | None:
        """Dispatch to the correct adapter based on api_type."""
        api_type = key_info["api_type"]
        try:
            if api_type == "music_qq":
                return await self._adapter_qq(query, key_info)
            if api_type == "music_netease":
                return await self._adapter_netease(query, key_info)
            # Generic/custom: use endpoint template
            return await self._adapter_generic(query, key_info)
        except Exception:
            return None

    async def _adapter_qq(
        self, query: str, key_info: dict[str, str]
    ) -> dict[str, object] | None:
        """QQ Music search API adapter."""
        import urllib.parse

        endpoint = (
            key_info["endpoint"] or "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
        )
        params = {
            "w": query,
            "format": "json",
            "p": "1",
            "n": "10",
            "t": "0",
        }
        url = f"{endpoint}?{urllib.parse.urlencode(params)}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
            r = await client.get(url)
        data = r.json()
        items: list[dict[str, str]] = []
        songs = data.get("data", {}).get("song", {}).get("list", [])
        for song in songs[:10]:
            items.append(
                {
                    "title": song.get("songname", song.get("name", "未知歌曲")),
                    "artist": _join_singers(song.get("singer", [])),
                    "album": song.get("albumname", ""),
                    "url": f"https://y.qq.com/n/ryqq/songDetail/{song.get('songmid', '')}",
                }
            )
        return {"source": key_info["name"], "items": items} if items else None

    async def _adapter_netease(
        self, query: str, key_info: dict[str, str]
    ) -> dict[str, object] | None:
        """NetEase Cloud Music search API adapter."""
        import urllib.parse

        endpoint = key_info["endpoint"] or "https://music.163.com/api/search/get"
        url = f"{endpoint}?s={urllib.parse.quote(query)}&type=1&limit=10&offset=0"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
            r = await client.get(url, headers={"Referer": "https://music.163.com"})
        data = r.json()
        items: list[dict[str, str]] = []
        songs = data.get("result", {}).get("songs", [])
        for song in songs[:10]:
            artists = ", ".join(
                a.get("name", "") for a in song.get("artists", []) if a.get("name")
            )
            items.append(
                {
                    "title": song.get("name", "未知歌曲"),
                    "artist": artists,
                    "album": song.get("album", {}).get("name", ""),
                    "url": f"https://music.163.com/song?id={song.get('id', '')}",
                }
            )
        return {"source": key_info["name"], "items": items} if items else None

    async def _adapter_generic(
        self, query: str, key_info: dict[str, str]
    ) -> dict[str, object] | None:
        """Generic music API adapter — uses endpoint template with {query}.

        Reads response mapping from config_json:
          {"results_path": "data.songs", "title_field": "name",
           "artist_field": "artist", "url_field": "url",
           "album_field": "album", "method": "GET",
           "headers": {"Authorization": "Bearer {api_key}"}}
        """
        import urllib.parse

        endpoint_tpl = key_info["endpoint"]
        if not endpoint_tpl:
            return None

        url = endpoint_tpl.replace("{query}", urllib.parse.quote(query))
        url = url.replace("{api_key}", urllib.parse.quote(key_info["api_key"]))

        config: dict[str, object] = {}
        try:
            config = json.loads(key_info["config_json"])
        except (json.JSONDecodeError, TypeError):
            pass

        method = str(config.get("method", "GET")).upper()
        results_path = str(config.get("results_path", "data"))
        title_field = str(config.get("title_field", "title"))
        artist_field = str(config.get("artist_field", "artist"))
        url_field = str(config.get("url_field", "url"))
        album_field = str(config.get("album_field", "album"))

        headers: dict[str, str] = {}
        raw_headers = config.get("headers")
        if isinstance(raw_headers, dict):
            for k, v in raw_headers.items():
                val = str(v).replace("{api_key}", key_info["api_key"])
                headers[k] = val

        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
            if method == "POST":
                r = await client.post(url, headers=headers)
            else:
                r = await client.get(url, headers=headers)

        data = r.json()

        # Navigate results_path (e.g. "data.songs")
        results: object = data
        for segment in results_path.split("."):
            if isinstance(results, dict):
                results = results.get(segment, [])
            else:
                results = []
                break

        if not isinstance(results, list):
            results = []

        items: list[dict[str, str]] = []
        for item in results[:10]:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "title": str(_deep_get(item, title_field, "未知歌曲")),
                    "artist": str(_deep_get(item, artist_field, "")),
                    "album": str(_deep_get(item, album_field, "")),
                    "url": str(_deep_get(item, url_field, "#")),
                }
            )
        return {"source": key_info["name"], "items": items} if items else None

    # ── Built-in free sources ──────────────────────────────────────

    async def _query_itunes(self, query: str) -> dict[str, object] | None:
        """iTunes Search API — free, no key required."""
        import urllib.parse

        url = (
            "https://itunes.apple.com/search?"
            f"term={urllib.parse.quote(query)}&media=music&limit=10&country=CN"
        )
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
                r = await client.get(url)
            data = r.json()
            items: list[dict[str, str]] = []
            for result in data.get("results", [])[:10]:
                items.append(
                    {
                        "title": result.get("trackName", "未知"),
                        "artist": result.get("artistName", ""),
                        "album": result.get("collectionName", ""),
                        "url": result.get(
                            "trackViewUrl", result.get("collectionViewUrl", "#")
                        ),
                    }
                )
            return {"source": "iTunes (内置)", "items": items} if items else None
        except Exception:
            return None

    async def _query_musicbrainz(self, query: str) -> dict[str, object] | None:
        """MusicBrainz API — free, open-source music metadata."""
        import urllib.parse

        url = (
            "https://musicbrainz.org/ws/2/recording/?"
            f"query={urllib.parse.quote(query)}&fmt=json&limit=10"
        )
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
                r = await client.get(
                    url,
                    headers={"User-Agent": "DataFinderAgentOS/1.0 (music search)"},
                )
            data = r.json()
            items: list[dict[str, str]] = []
            for rec in data.get("recordings", [])[:10]:
                artist = ""
                if rec.get("artist-credit"):
                    artist = ", ".join(
                        ac.get("name", "")
                        for ac in rec["artist-credit"]
                        if isinstance(ac, dict) and ac.get("name")
                    )
                items.append(
                    {
                        "title": rec.get("title", "未知"),
                        "artist": artist,
                        "album": rec.get("releases", [{}])[0].get("title", "")
                        if rec.get("releases")
                        else "",
                        "url": f"https://musicbrainz.org/recording/{rec.get('id', '')}",
                    }
                )
            return {"source": "MusicBrainz (内置)", "items": items} if items else None
        except Exception:
            return None

    async def _query_duckduckgo_music(self, query: str) -> dict[str, object] | None:
        """DuckDuckGo Instant Answer — free web search for music info."""
        import urllib.parse

        url = (
            "https://api.duckduckgo.com/?"
            f"q={urllib.parse.quote(query + ' music')}&format=json&no_redirect=1"
        )
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
                r = await client.get(url, follow_redirects=True)
            data = r.json()
            items: list[dict[str, str]] = []
            abstract = data.get("AbstractText", "")
            abstract_url = data.get("AbstractURL", "")
            if abstract:
                items.append(
                    {
                        "title": abstract[:120],
                        "artist": "",
                        "album": "",
                        "url": abstract_url or "#",
                    }
                )
            for topic in (data.get("RelatedTopics") or [])[:5]:
                if isinstance(topic, dict) and topic.get("Text"):
                    items.append(
                        {
                            "title": topic["Text"][:120],
                            "artist": "",
                            "album": "",
                            "url": topic.get("FirstURL", "#"),
                        }
                    )
            return {"source": "DuckDuckGo (内置)", "items": items} if items else None
        except Exception:
            return None


def _join_singers(singers: object) -> str:
    """Extract singer names from QQ Music singer list."""
    if not isinstance(singers, list):
        return ""
    names = []
    for s in singers:
        if isinstance(s, dict) and s.get("name"):
            names.append(s["name"])
    return ", ".join(names)


def _deep_get(obj: object, path: str, default: object = "") -> object:
    """Navigate nested dict by dot-separated path."""
    current = obj
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        else:
            return default
    return current if current is not None else default
