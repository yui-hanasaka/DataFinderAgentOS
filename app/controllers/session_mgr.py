from app.controllers.admin import AdminBaseHandler
from app.models.chat import ChatRepository

PER_PAGE = 20


class AdminSessionMgrHandler(AdminBaseHandler):
    def get(self) -> None:
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        sessions, total = ChatRepository.list_all_sessions(page, PER_PAGE)
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
