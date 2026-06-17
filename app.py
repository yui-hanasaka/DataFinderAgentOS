import os
import secrets

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
from app.controllers.auth import (
    LandingHandler,
    LoginHandler,
    LogoutHandler,
    RegisterHandler,
)
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
from app.controllers.digital_twin import (
    AdminDigitalTwinHandler,
    AdminDigitalTwinSceneHandler,
)
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
from app.controllers.watchtower_collect import WatchtowerCollectHandler
from app.models.db import init_db


def _resolve_cookie_secret() -> str:
    env_val = os.environ.get("COOKIE_SECRET", "").strip()
    dev = os.environ.get("DEV", "").lower() in ("1", "true", "yes")
    if env_val and len(env_val) >= 32:
        return env_val
    if not env_val and not dev:
        dev = True  # auto-dev: no COOKIE_SECRET set
    if dev:
        fallback = secrets.token_hex(32)
        print(
            "[DEV] COOKIE_SECRET not set — using ephemeral key (sessions reset on restart).\n"
            "      Set COOKIE_SECRET (>=32 chars) for production. Set DEV=1 for dev mode.",
            flush=True,
        )
        return fallback
    raise SystemExit(
        "FATAL: COOKIE_SECRET is missing or too short (>=32 chars required)."
        " Set the environment variable and restart."
    )


def app() -> tornado.web.Application:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dev = os.environ.get("DEV", "").lower() in ("1", "true", "yes")
    cookie_secret = _resolve_cookie_secret()
    routes: list[tuple[str, object]] = [
        # user auth
        (r"/", LandingHandler),
        (r"/login", LoginHandler),
        (r"/register", RegisterHandler),
        (r"/user/register", RegisterHandler),
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
        (r"/admin/watchtower/collect", WatchtowerCollectHandler),
        (r"/admin/warehouse", AdminWarehouseHandler),
        (r"/admin/deep", AdminDeepHandler),
        (r"/admin/apis", AdminApiKeyHandler),
        (r"/admin/sessions", AdminSessionMgrHandler),
        (r"/admin/conversations/(\d+)", AdminConversationDetailHandler),
        (r"/admin/screen", AdminScreenHandler),
        (r"/admin/settings", AdminSettingsHandler),
        (r"/admin/digital-twin", AdminDigitalTwinHandler),
        (r"/admin/digital-twin/scenes/(\d+)", AdminDigitalTwinSceneHandler),
        # api
        (r"/api/screen/data", ScreenDataApiHandler),
    ]

    return tornado.web.Application(
        routes,
        template_path=os.path.join(base_dir, "app", "templates"),
        static_path=os.path.join(base_dir, "app", "static"),
        cookie_secret=cookie_secret,
        login_url="/",
        xsrf_cookies=True,
        xsrf_cookie_kwargs={"httponly": False, "samesite": "Lax", "secure": not dev},
        debug=dev,
        autoreload=dev,
    )


if __name__ == "__main__":
    init_db()
    application = app()
    server = HTTPServer(
        application,
        max_body_size=2 * 1024 * 1024,
        max_buffer_size=2 * 1024 * 1024,
    )
    server.listen(10086)
    print("Server Started: http://localhost:10086/", flush=True)
    tornado.ioloop.IOLoop.current().start()
