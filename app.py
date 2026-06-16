# 主入口程序，主要是加载程序、加载和管理路由、配置访问控制以及服务器启动配置等

# v0.1版本：用于验证tornado框架的最小示例，主要是验证路由、程序加载、服务器启动
import os
import tornado.web
import tornado.ioloop
from tornado.httpserver import HTTPServer

from app.controllers.auth import LoginHandler,LogoutHandler
from app.controllers.home import HomeHandler
from app.models.db import init_db




# web应用
def app():
	base_dir = os.path.dirname(os.path.abspath(__file__))
	settings = dict(
		template_path=os.path.join(base_dir,"app","templates"),
		static_path=os.path.join(base_dir,"app","static"),
		cookie_secret="demo-cookie-secret-change-me",
		login_url="/",
		xsrf_cookies=True,
		debug="True",
		autoreload=True
	)

	return tornado.web.Application(
		[
			("/",LoginHandler), #get
			("/home",HomeHandler),
			("/user/login",LoginHandler),#post
			("/user/logout",LogoutHandler)
		],
		**settings
	)


if __name__ == "__main__":
	init_db()
	app = app()
	server = HTTPServer(app)
	server.listen(10086)
	print("Server Started:http://localhost:10086/",flush=True)
	tornado.ioloop.IOLoop.current().start()