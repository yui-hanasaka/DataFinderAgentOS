from app.controllers.admin import AdminBaseHandler
from app.models.employee import EmployeeRepository
from app.models.model_engine import ModelRepository

PER_PAGE = 20


class AdminEmployeeHandler(AdminBaseHandler):
    def get(self):
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        employees, total = EmployeeRepository.list_employees(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_emp = (
            EmployeeRepository.get_employee(int(edit_id)) if edit_id.isdigit() else None
        )
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
            all_models=all_models,
            all_skills=all_skills,
            msg=self._message(),
        )

    def post(self):
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
                int(emp_id), name, avatar, model_id, system_prompt, skills_list, status
            )
            return self._redirect_with_message(
                "/admin/employees", msg or "已更新" if ok else msg
            )
        ok, msg = EmployeeRepository.create_employee(
            name, avatar, model_id, system_prompt, skills_list, status
        )
        self._redirect_with_message("/admin/employees", msg or "已新增" if ok else msg)
