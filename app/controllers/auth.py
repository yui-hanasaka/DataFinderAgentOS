from app.controllers.base import BaseHandler
from app.models.rate_limit import check_rate_limit
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
        self.render("web/login.html", title="用户登录", error=None)

    def post(self):
        ip = self.request.remote_ip
        if not check_rate_limit(f"login:{ip}", 10, 600):
            self.set_status(429)
            return self.render(
                "web/login.html", title="用户登录", error="请求过于频繁，请稍后再试"
            )

        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "").strip()
        if not username or not password:
            self.set_status(400)
            return self.render(
                "web/login.html", title="用户登录", error="请输入用户名或密码"
            )

        if not UserRepository.verify_user(username, password):
            self.set_status(401)
            return self.render(
                "web/login.html", title="用户登录", error="用户名或密码错误"
            )

        self.set_auth_cookie("username", username)
        self.redirect("/home")


class RegisterHandler(BaseHandler):
    def get(self):
        if self.get_secure_cookie("username"):
            return self.redirect("/home")
        self.render("web/register.html", title="用户注册", error=None)

    def post(self):
        ip = self.request.remote_ip
        if not check_rate_limit(f"register:{ip}", 5, 3600):
            self.set_status(429)
            return self.render(
                "web/register.html",
                title="用户注册",
                error="注册请求过于频繁，请稍后再试",
            )

        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "").strip()
        confirm_password = self.get_body_argument("confirm_password", "").strip()
        if not username:
            self.set_status(400)
            return self.render(
                "web/register.html", title="用户注册", error="请输入用户名"
            )
        if len(password) < 8:
            self.set_status(400)
            return self.render(
                "web/register.html", title="用户注册", error="密码长度不能少于8位"
            )
        if password != confirm_password:
            self.set_status(400)
            return self.render(
                "web/register.html", title="用户注册", error="两次输入的密码不一致"
            )

        if not UserRepository.create_user(username, password):
            self.set_status(409)
            return self.render(
                "web/register.html", title="用户注册", error="用户名已存在"
            )

        self.redirect("/login")


class LogoutHandler(BaseHandler):
    def post(self):
        self.clear_auth_cookie("username")
        self.redirect("/")
