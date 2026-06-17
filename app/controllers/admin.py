from app.controllers.base import BaseHandler
from app.models.admin import PER_PAGE, AdminRepository


class AdminLoginHandler(BaseHandler):
    def get(self):
        if self.get_secure_cookie("admin_username"):
            return self.redirect("/admin/home")
        self.render("admin/login.html", title="后台登录", error=None)

    def post(self):
        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "").strip()
        if not AdminRepository.verify_admin(username, password):
            self.set_status(401)
            return self.render(
                "admin/login.html", title="后台登录", error="用户名或密码错误"
            )

        self.set_secure_cookie("admin_username", username)
        self.redirect("/admin/home")


class AdminBaseHandler(BaseHandler):
    def get_current_user(self):
        admin_username = self.get_secure_cookie("admin_username")
        if not admin_username:
            return None
        return admin_username.decode("utf-8")

    def prepare(self):
        if not self.current_user:
            return self.redirect("/admin/login")

    def _page(self):
        try:
            return max(int(self.get_query_argument("page", "1")), 1)
        except ValueError:
            return 1

    def _message(self):
        return self.get_query_argument("msg", "")

    def _redirect_with_message(self, url, message):
        self.redirect(f"{url}?msg={message}")


class AdminHomeHandler(AdminBaseHandler):
    def get(self):
        from app.models.db import get_connection
        from app.models.model_engine import ModelRepository

        with get_connection() as conn:
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            admin_count = conn.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0]
            session_count = conn.execute(
                "SELECT COUNT(*) FROM chat_sessions"
            ).fetchone()[0]
            item_count = conn.execute(
                "SELECT COUNT(*) FROM watchtower_items"
            ).fetchone()[0]
            recent_sessions = conn.execute(
                "SELECT cs.id, cs.title, cs.created_at, u.username "
                "FROM chat_sessions cs LEFT JOIN users u ON u.id=cs.user_id "
                "ORDER BY cs.id DESC LIMIT 8"
            ).fetchall()
        usage = ModelRepository.usage_summary()
        total_calls = sum(int(r["calls"]) for r in usage)
        self.render(
            "admin/home.html",
            title="后台管理",
            username=self.current_user,
            user_count=user_count,
            admin_count=admin_count,
            session_count=session_count,
            item_count=item_count,
            total_calls=total_calls,
            recent_sessions=recent_sessions,
        )


class AdminLogoutHandler(BaseHandler):
    def post(self):
        self.clear_cookie("admin_username")
        self.redirect("/admin/login")


class AdminRoleHandler(AdminBaseHandler):
    def get(self):
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        roles, total = AdminRepository.list_roles(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_role = (
            AdminRepository.get_role(int(edit_id)) if edit_id.isdigit() else None
        )
        checked_menu_ids = (
            AdminRepository.get_role_menu_ids(int(edit_id)) if edit_id.isdigit() else []
        )
        self.render(
            "admin/roles.html",
            title="角色管理",
            username=self.current_user,
            roles=roles,
            total=total,
            page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            edit_role=edit_role,
            menus=AdminRepository.list_all_menus(),
            checked_menu_ids=checked_menu_ids,
            msg=self._message(),
        )

    def post(self):
        action = self.get_body_argument("action", "")
        role_id = self.get_body_argument("id", "")
        if action == "delete" and role_id.isdigit():
            ok, msg = AdminRepository.delete_role(int(role_id))
            return self._redirect_with_message(
                "/admin/roles", msg or "角色已删除" if ok else msg
            )

        menu_ids = self.get_body_arguments("menu_ids")
        if role_id.isdigit():
            ok, msg = AdminRepository.update_role(
                int(role_id),
                self.get_body_argument("role_name", "").strip(),
                self.get_body_argument("role_type", "manager"),
                self.get_body_argument("description", "").strip(),
                self.get_body_argument("status", "enabled"),
                menu_ids,
            )
            return self._redirect_with_message(
                "/admin/roles", msg or "角色已更新" if ok else msg
            )

        ok, msg = AdminRepository.create_role(
            self.get_body_argument("role_code", "").strip(),
            self.get_body_argument("role_name", "").strip(),
            self.get_body_argument("role_type", "manager"),
            self.get_body_argument("description", "").strip(),
            menu_ids,
        )
        self._redirect_with_message("/admin/roles", msg or "角色已新增" if ok else msg)


class AdminUserHandler(AdminBaseHandler):
    def get(self):
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        users, total = AdminRepository.list_users(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_user = (
            AdminRepository.get_user(int(edit_id)) if edit_id.isdigit() else None
        )
        self.render(
            "admin/users.html",
            title="用户管理",
            username=self.current_user,
            users=users,
            total=total,
            page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            edit_user=edit_user,
            roles=AdminRepository.list_all_roles(),
            msg=self._message(),
        )

    def post(self):
        action = self.get_body_argument("action", "")
        user_id = self.get_body_argument("id", "")
        if action == "delete" and user_id.isdigit():
            ok, msg = AdminRepository.delete_user(int(user_id))
            return self._redirect_with_message(
                "/admin/users", msg or "用户已删除" if ok else msg
            )

        if user_id.isdigit():
            ok, msg = AdminRepository.update_user(
                int(user_id),
                self.get_body_argument("display_name", "").strip(),
                int(self.get_body_argument("role_id", "0")),
                self.get_body_argument("status", "enabled"),
                self.get_body_argument("password", "").strip(),
            )
            return self._redirect_with_message(
                "/admin/users", msg or "用户已更新" if ok else msg
            )

        ok, msg = AdminRepository.create_user(
            self.get_body_argument("username", "").strip(),
            self.get_body_argument("password", "").strip(),
            self.get_body_argument("display_name", "").strip(),
            int(self.get_body_argument("role_id", "0")),
            self.get_body_argument("status", "enabled"),
        )
        self._redirect_with_message("/admin/users", msg or "用户已新增" if ok else msg)


class AdminMenuHandler(AdminBaseHandler):
    def get(self):
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        menus, total = AdminRepository.list_menus(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_menu = (
            AdminRepository.get_menu(int(edit_id)) if edit_id.isdigit() else None
        )
        self.render(
            "admin/menus.html",
            title="功能管理",
            username=self.current_user,
            menus=menus,
            total=total,
            page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            edit_menu=edit_menu,
            all_menus=AdminRepository.list_all_menus(),
            msg=self._message(),
        )

    def post(self):
        action = self.get_body_argument("action", "")
        menu_id = self.get_body_argument("id", "")
        if action == "delete" and menu_id.isdigit():
            ok, msg = AdminRepository.delete_menu(int(menu_id))
            return self._redirect_with_message(
                "/admin/menus", msg or "功能已删除" if ok else msg
            )

        if menu_id.isdigit():
            ok, msg = AdminRepository.update_menu(
                int(menu_id),
                self.get_body_argument("menu_name", "").strip(),
                self.get_body_argument("icon", "").strip(),
                self.get_body_argument("url", "").strip(),
                int(self.get_body_argument("sort_order", "0") or 0),
                self.get_body_argument("status", "enabled"),
                int(self.get_body_argument("parent_id", "0") or 0),
            )
            return self._redirect_with_message(
                "/admin/menus", msg or "功能已更新" if ok else msg
            )

        ok, msg = AdminRepository.create_menu(
            self.get_body_argument("menu_code", "").strip(),
            self.get_body_argument("menu_name", "").strip(),
            self.get_body_argument("icon", "").strip(),
            self.get_body_argument("url", "").strip(),
            int(self.get_body_argument("sort_order", "0") or 0),
            int(self.get_body_argument("parent_id", "0") or 0),
        )
        self._redirect_with_message("/admin/menus", msg or "功能已新增" if ok else msg)
