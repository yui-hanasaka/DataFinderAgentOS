import tornado.web
from app.controllers.base import BaseHandler

class HomeHandler(BaseHandler):
	@tornado.web.authenticated
	def get(self):
		self.render("web/index.html",title="首页",username=self.current_user)