from app.controllers.admin import AdminBaseHandler
from app.models.chat import ChatRepository

PER_PAGE = 20


class AdminSessionMgrHandler(AdminBaseHandler):
    def get(self) -> None:
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        sessions, total = ChatRepository.list_all_sessions(
            page, PER_PAGE, keyword=keyword
        )
        self.render(
            "admin/sessions.html",
            title="会话管理",
            username=self.current_user,
            sessions=sessions,
            total=total,
            page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            msg=self._message(),
        )

    def post(self) -> None:
        action = self.get_body_argument("action", "")
        sess_id = self.get_body_argument("id", "")
        if action == "delete" and sess_id.isdigit():
            ChatRepository.delete_session(int(sess_id))
            return self._redirect_with_message("/admin/sessions", "会话已删除")
        if action == "batch_delete":
            ids = self.get_body_arguments("ids")
            numeric_ids = [int(i) for i in ids if i.isdigit()]
            if numeric_ids:
                count = ChatRepository.delete_sessions_admin(numeric_ids)
                return self._redirect_with_message(
                    "/admin/sessions", f"已删除 {count} 个会话"
                )
            return self._redirect_with_message("/admin/sessions", "请选择要删除的会话")
        self._redirect_with_message("/admin/sessions", "")


class AdminConversationDetailHandler(AdminBaseHandler):
    def get(self, session_id: str) -> None:
        session = ChatRepository.get_session(int(session_id))
        if not session:
            return self.redirect("/admin/sessions")
        messages = ChatRepository.list_messages(int(session_id))
        self.render(
            "admin/conversations.html",
            title="对话详情",
            username=self.current_user,
            session=session,
            messages=messages,
        )
