from app.controllers.admin import AdminBaseHandler
from app.models.admin import AdminRepository
from app.models.rate_limit import check_rate_limit


class AdminPermissionHandler(AdminBaseHandler):
    def get(self) -> None:
        roles = AdminRepository.list_all_roles()
        menus = AdminRepository.list_all_menus()
        role_menu_map = {
            r["id"]: set(AdminRepository.get_role_menu_ids(r["id"])) for r in roles
        }
        self.render(
            "admin/permissions.html",
            title="权限管理",
            username=self.current_user,
            roles=roles,
            menus=menus,
            role_menu_map=role_menu_map,
            msg=self._message(),
        )

    def post(self) -> None:
        if not check_rate_limit(f"permissions:{self.current_user}", 20, 60):
            self.set_status(429)
            self.write({"error": "操作过于频繁，请稍后再试"})
            return

        role_id = self.get_body_argument("role_id", "")
        menu_ids = self.get_body_arguments("menu_ids")
        if role_id.isdigit():
            from app.models.db import get_connection

            with get_connection() as conn:
                AdminRepository._replace_role_menus(conn, int(role_id), menu_ids)
            return self._redirect_with_message("/admin/permissions", "权限已保存")
        self._redirect_with_message("/admin/permissions", "参数错误")
