import tornado.web

from app.controllers.base import BaseHandler
from app.models.chat import ChatRepository
from app.models.db import get_connection


class HomeHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username=?", (self.current_user,)
            ).fetchone()
        user_id = row["id"] if row else 0
        recent_sessions, _ = ChatRepository.list_sessions(user_id, page=1)
        self.render(
            "web/index.html",
            title="首页",
            username=self.current_user,
            recent_sessions=recent_sessions[:5],
        )
