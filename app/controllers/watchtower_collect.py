from app.controllers.admin import AdminBaseHandler


class WatchtowerCollectHandler(AdminBaseHandler):
    def get(self):
        self.render(
            "admin/watchtower_collect.html",
            title="瞭望采集",
            username=self.current_user,
            sources=[],
            msg=self._message(),
        )

    def post(self):
        self._redirect_with_message("/admin/watchtower/collect", "功能开发中")
