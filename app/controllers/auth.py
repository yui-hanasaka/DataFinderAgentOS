import tornado.web
from app.controllers.base import BaseHandler
from app.models.user import UserRepository

class LoginHandler(BaseHandler):
	def get(self):
		self.render("web\\login.html",title="登录",error=None)

	def post(self):
		username = self.get_body_argument("username","")
		password = self.get_body_argument("password","")
		if not username or not password:
			self.set_status(400)
			return self.render("web\\login.html",title="登录",error="请输入用户名或密码")

		if not UserRepository.verify_user(username,password):
			self.set_status(401)
			return self.render("web\\login.html",title="登录",error="用户名或密码错误")

		self.set_secure_cookie("username",username)
		self.redirect("/home") #后台地址

class LogoutHandler(BaseHandler):
	def post(self):
		self.clear_cookie("username")
		self.redirect("/") #登录地址