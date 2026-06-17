from app.controllers.admin import AdminBaseHandler
from app.models.digital_twin import DigitalTwinRepository


class AdminDigitalTwinHandler(AdminBaseHandler):
    def get(self):
        scenes = DigitalTwinRepository.list_scenes()
        edit_id = self.get_query_argument("edit", "")
        edit_scene = (
            DigitalTwinRepository.get_scene(int(edit_id)) if edit_id.isdigit() else None
        )
        self.render(
            "admin/digital_twin.html",
            title="数字孪生",
            username=self.current_user,
            scenes=scenes,
            edit_scene=edit_scene,
            msg=self._message(),
        )

    def post(self):
        action = self.get_body_argument("action", "")
        scene_id = self.get_body_argument("id", "")

        if action == "delete" and scene_id.isdigit():
            ok, msg = DigitalTwinRepository.delete_scene(int(scene_id))
            return self._redirect_with_message(
                "/admin/digital-twin", msg or "场景已删除" if ok else msg
            )

        name = self.get_body_argument("name", "").strip()
        description = self.get_body_argument("description", "").strip()
        scene_json = self.get_body_argument("scene_json", "{}").strip()
        status = self.get_body_argument("status", "enabled").strip()

        if not name:
            return self._redirect_with_message(
                "/admin/digital-twin", "场景名称不能为空"
            )

        if scene_id.isdigit():
            ok, msg = DigitalTwinRepository.update_scene(
                int(scene_id),
                {
                    "name": name,
                    "description": description,
                    "scene_json": scene_json,
                    "status": status,
                },
            )
            return self._redirect_with_message(
                "/admin/digital-twin", msg or "场景已更新" if ok else msg
            )

        ok, msg = DigitalTwinRepository.create_scene(
            {
                "name": name,
                "description": description,
                "scene_json": scene_json,
                "status": status,
            }
        )
        self._redirect_with_message(
            "/admin/digital-twin", msg or "场景已创建" if ok else msg
        )


class AdminDigitalTwinSceneHandler(AdminBaseHandler):
    def get(self, scene_id):
        scene = DigitalTwinRepository.get_scene(int(scene_id))
        if not scene:
            return self._redirect_with_message("/admin/digital-twin", "场景不存在")
        models = DigitalTwinRepository.list_models(int(scene_id))
        edit_model_id = self.get_query_argument("edit_model", "")
        edit_model = (
            DigitalTwinRepository.get_model(int(edit_model_id))
            if edit_model_id.isdigit()
            else None
        )
        self.render(
            "admin/digital_twin_scene.html",
            title="场景详情",
            username=self.current_user,
            scene=scene,
            models=models,
            edit_model=edit_model,
            msg=self._message(),
        )

    def post(self, scene_id):
        action = self.get_body_argument("action", "")
        model_id = self.get_body_argument("model_id", "")

        if action == "delete_model" and model_id.isdigit():
            ok, msg = DigitalTwinRepository.delete_model(int(model_id))
            return self._redirect_with_message(
                f"/admin/digital-twin/scenes/{scene_id}",
                msg or "模型已删除" if ok else msg,
            )

        if action == "update_scene":
            name = self.get_body_argument("name", "").strip()
            description = self.get_body_argument("description", "").strip()
            scene_json = self.get_body_argument("scene_json", "{}").strip()
            status = self.get_body_argument("status", "enabled").strip()
            if not name:
                return self._redirect_with_message(
                    f"/admin/digital-twin/scenes/{scene_id}",
                    "场景名称不能为空",
                )
            ok, msg = DigitalTwinRepository.update_scene(
                int(scene_id),
                {
                    "name": name,
                    "description": description,
                    "scene_json": scene_json,
                    "status": status,
                },
            )
            return self._redirect_with_message(
                f"/admin/digital-twin/scenes/{scene_id}",
                msg or "场景已更新" if ok else msg,
            )

        # Default: create or update model
        name = self.get_body_argument("name", "").strip()
        model_type = self.get_body_argument("model_type", "primitive").strip()
        asset_url = self.get_body_argument("asset_url", "").strip()
        transform_json = self.get_body_argument("transform_json", "{}").strip()
        metadata_json = self.get_body_argument("metadata_json", "{}").strip()

        if not name:
            return self._redirect_with_message(
                f"/admin/digital-twin/scenes/{scene_id}",
                "模型名称不能为空",
            )

        if model_id.isdigit():
            ok, msg = DigitalTwinRepository.update_model(
                int(model_id),
                {
                    "name": name,
                    "model_type": model_type,
                    "asset_url": asset_url,
                    "transform_json": transform_json,
                    "metadata_json": metadata_json,
                },
            )
            return self._redirect_with_message(
                f"/admin/digital-twin/scenes/{scene_id}",
                msg or "模型已更新" if ok else msg,
            )

        ok, msg = DigitalTwinRepository.create_model(
            {
                "scene_id": int(scene_id),
                "name": name,
                "model_type": model_type,
                "asset_url": asset_url,
                "transform_json": transform_json,
                "metadata_json": metadata_json,
            }
        )
        self._redirect_with_message(
            f"/admin/digital-twin/scenes/{scene_id}",
            msg or "模型已创建" if ok else msg,
        )
