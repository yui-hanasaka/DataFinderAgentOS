# 整个控制层的基类，用于继承RequestHandler,对安全配置等做统一处理
import os

import tornado.web


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self) -> str | None:
        username = self.get_secure_cookie("username")
        if not username:
            return None
        return username.decode("utf-8")

    def _is_production(self) -> bool:
        dev = os.environ.get("DEV", "").lower() in ("1", "true", "yes")
        return not dev and (
            os.environ.get("PYTHON_ENV", "") == "production"
            or self.request.protocol == "https"
        )

    def set_auth_cookie(self, name: str, value: str) -> None:
        self.set_secure_cookie(
            name,
            value,
            httponly=True,
            samesite="Lax",
            secure=self._is_production(),
            path="/",
        )

    def clear_auth_cookie(self, name: str) -> None:
        self.clear_cookie(
            name,
            path="/",
            httponly=True,
            samesite="Lax",
            secure=self._is_production(),
        )
