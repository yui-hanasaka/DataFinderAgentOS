import json

from app.controllers.admin import AdminBaseHandler
from app.models.employee import EmployeeRepository
from app.models.model_engine import ModelRepository

PER_PAGE = 20


class AdminEmployeeHandler(AdminBaseHandler):
    def get(self) -> None:
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        employees, total = EmployeeRepository.list_employees(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_emp = (
            EmployeeRepository.get_employee(int(edit_id)) if edit_id.isdigit() else None
        )
        edit_skill_ids: list[int] = []
        if edit_emp:
            try:
                raw = json.loads(edit_emp["skills"] or "[]")
                edit_skill_ids = [int(x) for x in raw]
            except (json.JSONDecodeError, ValueError):
                edit_skill_ids = []
        all_models, _ = ModelRepository.list_models(page=1, per_page=100)
        from app.models.skill import SkillRepository

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
            ok, msg = EmployeeRepository.delete_employee(int(emp_id))
            return self._redirect_with_message(
                "/admin/employees", msg or "已删除" if ok else msg
            )
        skills_list = self.get_body_arguments("skills")
        name = self.get_body_argument("name", "").strip()
        avatar = self.get_body_argument("avatar", "🤖").strip()
        model_id = int(self.get_body_argument("model_id", "0") or 0)
        system_prompt = self.get_body_argument("system_prompt", "").strip()
        status = self.get_body_argument("status", "enabled")
        if emp_id.isdigit():
            ok, msg = EmployeeRepository.update_employee(
                int(emp_id),
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
