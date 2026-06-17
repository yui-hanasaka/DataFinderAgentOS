import json
import logging

from app.controllers.admin import AdminBaseHandler
from app.models.employee import EmployeeRepository
from app.models.model_engine import ModelRepository
from app.models.skill import SkillRepository
from app.models.validators import parse_int

logger = logging.getLogger(__name__)

PER_PAGE = 20


class AdminEmployeeHandler(AdminBaseHandler):
    def get(self) -> None:
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        employees, total = EmployeeRepository.list_employees(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_emp = (
            EmployeeRepository.get_employee(parse_int(edit_id))
            if edit_id.isdigit()
            else None
        )
        edit_skill_ids: list[int] = []
        if edit_emp:
            try:
                raw = json.loads(edit_emp["skills"] or "[]")
                edit_skill_ids = [parse_int(x) for x in raw]
            except (json.JSONDecodeError, ValueError):
                edit_skill_ids = []
        all_models, _ = ModelRepository.list_models(page=1, per_page=100)
        all_skills = SkillRepository.list_all_active()
        self.render(
            "admin/employees.html",
            title="数字员工",
            username=self.current_user,
            employees=employees,
            total=total,
            page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            edit_employee=edit_emp,
            edit_skill_ids=edit_skill_ids,
            all_models=all_models,
            all_skills=all_skills,
            msg=self._message(),
        )

    def post(self) -> None:
        action = self.get_body_argument("action", "")
        emp_id = self.get_body_argument("id", "")
        if action == "delete" and emp_id.isdigit():
            ok, msg = EmployeeRepository.delete_employee(parse_int(emp_id))
            return self._redirect_with_message(
                "/admin/employees", msg or "已删除" if ok else msg
            )
        skills_list = self.get_body_arguments("skills")
        all_skills = SkillRepository.list_all_active()
        valid_ids = {str(s["id"]) for s in all_skills}
        filtered_skills = [s for s in skills_list if s in valid_ids]
        removed = [s for s in skills_list if s not in valid_ids]
        if removed:
            logger.warning("员工表单包含无效技能ID，已移除: %s", ", ".join(removed))
        skills_list = filtered_skills
        name = self.get_body_argument("name", "").strip()
        avatar = self.get_body_argument("avatar", "🤖").strip()
        model_id = parse_int(self.get_body_argument("model_id", "0"), 0)
        system_prompt = self.get_body_argument("system_prompt", "").strip()
        status = self.get_body_argument("status", "enabled")
        if emp_id.isdigit():
            ok, msg = EmployeeRepository.update_employee(
                parse_int(emp_id),
                {
                    "name": name,
                    "avatar": avatar,
                    "model_id": model_id,
                    "system_prompt": system_prompt,
                    "skills_list": skills_list,
                    "status": status,
                },
            )
            return self._redirect_with_message(
                "/admin/employees", msg or "已更新" if ok else msg
            )
        ok, msg = EmployeeRepository.create_employee(
            {
                "name": name,
                "avatar": avatar,
                "model_id": model_id,
                "system_prompt": system_prompt,
                "skills_list": skills_list,
                "status": status,
            }
        )
        self._redirect_with_message("/admin/employees", msg or "已新增" if ok else msg)
