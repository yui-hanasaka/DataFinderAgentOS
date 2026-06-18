import json

from app.controllers.admin import AdminBaseHandler
from app.models.skill import SkillRepository

PER_PAGE = 20


class AdminSkillHandler(AdminBaseHandler):
    def get(self) -> None:
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        skills, total = SkillRepository.list_skills(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_skill = (
            SkillRepository.get_skill(int(edit_id)) if edit_id.isdigit() else None
        )
        self.render(
            "admin/skills.html",
            title="技能管理",
            username=self.current_user,
            skills=skills,
            total=total,
            page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            edit_skill=edit_skill,
            msg=self._message(),
        )

    def post(self) -> None:
        action = self.get_body_argument("action", "")
        skill_id = self.get_body_argument("id", "")
        if action == "delete" and skill_id.isdigit():
            ok, msg = SkillRepository.delete_skill(int(skill_id))
            return self._redirect_with_message(
                "/admin/skills", msg or "已删除" if ok else msg
            )
        code = self.get_body_argument("code", "").strip()
        name = self.get_body_argument("name", "").strip()
        skill_type = self.get_body_argument("skill_type", "builtin")
        description = self.get_body_argument("description", "").strip()
        api_url = self.get_body_argument("api_url", "").strip()
        http_method = self.get_body_argument("http_method", "GET").strip()
        parameters_json = self.get_body_argument("parameters_json", "[]").strip()
        headers_json = self.get_body_argument("headers_json", "{}").strip()
        config_json = self.get_body_argument("config_json", "{}").strip()

        # Validate JSON fields
        for field_name, field_val in [
            ("parameters_json", parameters_json),
            ("headers_json", headers_json),
            ("config_json", config_json),
        ]:
            try:
                json.loads(field_val)
            except json.JSONDecodeError:
                return self._redirect_with_message(
                    "/admin/skills", f"{field_name} 格式无效，请输入有效的 JSON"
                )

        status = self.get_body_argument("status", "enabled")
        data: dict[str, object] = {
            "code": code,
            "name": name,
            "skill_type": skill_type,
            "description": description,
            "api_url": api_url,
            "http_method": http_method,
            "parameters_json": parameters_json,
            "headers_json": headers_json,
            "config_json": config_json,
            "status": status,
        }
        if skill_id.isdigit():
            ok, msg = SkillRepository.update_skill(int(skill_id), data)
            return self._redirect_with_message(
                "/admin/skills", msg or "已更新" if ok else msg
            )
        ok, msg = SkillRepository.create_skill(data)
        self._redirect_with_message("/admin/skills", msg or "已新增" if ok else msg)
