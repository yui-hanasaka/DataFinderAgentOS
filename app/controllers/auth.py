from app.controllers.base import BaseHandler
from app.models.admin import AdminRepository
from app.models.user import UserRepository


class LandingHandler(BaseHandler):
    def get(self):
        if self.get_secure_cookie("username"):
            return self.redirect("/home")
        if self.get_secure_cookie("admin_username"):
            return self.redirect("/admin/home")
        self.render("web/landing.html", title="DataFinder AgentOS")


class LoginHandler(BaseHandler):
    def get(self):
        if self.get_secure_cookie("username"):
            return self.redirect("/home")
        self.render("web/login.html", title="登录", error=None)

    def post(self):
        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "").strip()
        if not username or not password:
            self.set_status(400)
            return self.render(
                "web/login.html", title="登录", error="请输入用户名或密码"
            )

        if AdminRepository.verify_admin(username, password):
            self.set_secure_cookie("admin_username", username)
            return self.redirect("/admin/home")

        if not UserRepository.verify_user(username, password):
            self.set_status(401)
            return self.render("web/login.html", title="登录", error="用户名或密码错误")

        self.set_secure_cookie("username", username)
        self.redirect("/home")


class LogoutHandler(BaseHandler):
    def post(self):
        self.clear_cookie("username")
        self.redirect("/")
