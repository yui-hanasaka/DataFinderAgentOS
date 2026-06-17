from app.controllers.admin import AdminBaseHandler


class AdminDigitalTwinHandler(AdminBaseHandler):
    def get(self):
        self.render(
            "admin/digital_twin.html",
            title="数字孪生",
            username=self.current_user,
            scenes=[],
            msg=self._message(),
        )

    def post(self):
        self._redirect_with_message("/admin/digital-twin", "功能开发中")


class AdminDigitalTwinSceneHandler(AdminBaseHandler):
    def get(self, scene_id):
        self.render(
            "admin/digital_twin_scene.html",
            title="场景详情",
            username=self.current_user,
            scene=None,
            msg="功能开发中",
        )
