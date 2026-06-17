import os

import tornado.ioloop
import tornado.web
from tornado.httpserver import HTTPServer

from app.controllers.admin import (
    AdminHomeHandler,
    AdminLoginHandler,
    AdminLogoutHandler,
    AdminMenuHandler,
    AdminRoleHandler,
    AdminUserHandler,
)
from app.controllers.api_key import AdminApiKeyHandler
from app.controllers.ask import AskHomeHandler, AskQueryHandler
from app.controllers.auth import LandingHandler, LoginHandler, LogoutHandler
from app.controllers.chat import (
    ChatBatchDeleteHandler,
    ChatDeleteHandler,
    ChatExportHandler,
    ChatHomeHandler,
    ChatNewHandler,
    ChatSendHandler,
    ChatSessionHandler,
)
from app.controllers.deep import AdminDeepHandler
from app.controllers.employee import AdminEmployeeHandler
from app.controllers.home import HomeHandler
from app.controllers.model_engine import (
    AdminModelChatHandler,
    AdminModelEngineHandler,
    AdminModelTestHandler,
)
from app.controllers.permissions import AdminPermissionHandler
from app.controllers.screen import AdminScreenHandler, ScreenDataApiHandler
from app.controllers.session_mgr import (
    AdminConversationDetailHandler,
    AdminSessionMgrHandler,
)
from app.controllers.settings import AdminSettingsHandler
from app.controllers.skill import AdminSkillHandler
from app.controllers.warehouse import AdminWarehouseHandler
from app.controllers.watchtower import AdminWatchtowerHandler
from app.models.db import init_db


def app():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dev = os.environ.get("DEV", "").lower() in ("1", "true", "yes")
    routes: list[tuple[str, object]] = [
        # user auth
        (r"/", LandingHandler),
        (r"/login", LoginHandler),
        (r"/user/login", LoginHandler),
        (r"/user/logout", LogoutHandler),
        (r"/home", HomeHandler),
        # user chat
        (r"/chat", ChatHomeHandler),
        (r"/chat/new", ChatNewHandler),
        (r"/chat/session/(\d+)", ChatSessionHandler),
        (r"/chat/delete/(\d+)", ChatDeleteHandler),
        (r"/chat/batch-delete", ChatBatchDeleteHandler),
        (r"/chat/send/(\d+)", ChatSendHandler),
        (r"/chat/export/(\d+)", ChatExportHandler),
        # user ask
        (r"/ask", AskHomeHandler),
        (r"/ask/query", AskQueryHandler),
        # admin auth
        (r"/admin/login", AdminLoginHandler),
        (r"/admin/logout", AdminLogoutHandler),
        # admin core
        (r"/admin/home", AdminHomeHandler),
        (r"/admin/users", AdminUserHandler),
        (r"/admin/roles", AdminRoleHandler),
        (r"/admin/menus", AdminMenuHandler),
        (r"/admin/permissions", AdminPermissionHandler),
        # admin model engine
        (r"/admin/models", AdminModelEngineHandler),
        (r"/admin/models/(\d+)/test", AdminModelTestHandler),
        (r"/admin/models/(\d+)/chat", AdminModelChatHandler),
        # admin business
        (r"/admin/employees", AdminEmployeeHandler),
        (r"/admin/skills", AdminSkillHandler),
        (r"/admin/watchtower", AdminWatchtowerHandler),
        (r"/admin/warehouse", AdminWarehouseHandler),
        (r"/admin/deep", AdminDeepHandler),
        (r"/admin/apis", AdminApiKeyHandler),
        (r"/admin/sessions", AdminSessionMgrHandler),
        (r"/admin/conversations/(\d+)", AdminConversationDetailHandler),
        (r"/admin/screen", AdminScreenHandler),
        (r"/admin/settings", AdminSettingsHandler),
        # api
        (r"/api/screen/data", ScreenDataApiHandler),
    ]

    return tornado.web.Application(
        routes,
        template_path=os.path.join(base_dir, "app", "templates"),
        static_path=os.path.join(base_dir, "app", "static"),
        cookie_secret="demo-cookie-secret-change-me",
        login_url="/",
        xsrf_cookies=True,
        debug=dev,
        autoreload=dev,
    )


if __name__ == "__main__":
    init_db()
    application = app()
    server = HTTPServer(application)
    server.listen(10086)
    print("Server Started: http://localhost:10086/", flush=True)
    tornado.ioloop.IOLoop.current().start()
