import re

from app.controllers.base import BaseHandler
from app.models.admin import PER_PAGE, AdminRepository
from app.models.rate_limit import check_rate_limit


class AdminLoginHandler(BaseHandler):
    def get(self) -> None:
        if self.get_secure_cookie("admin_username"):
            self.redirect("/admin/home")
            return
        self.render("admin/login.html", title="后台登录", error=None)

    def post(self) -> None:
        ip = self.request.remote_ip
        if not check_rate_limit(f"admin_login:{ip}", 10, 600):
            self.set_status(429)
            self.render(
                "admin/login.html", title="后台登录", error="请求过于频繁，请稍后再试"
            )
            return

        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "").strip()

        # Per-account rate limit
        if username:
            if not check_rate_limit(f"admin_login_account:{username}", 5, 60):
                self.set_status(429)
                return self.render(
                    "admin/login.html",
                    title="后台登录",
                    error="该账号登录尝试过于频繁，请稍后再试",
                )

        ok, err_msg, admin_row = AdminRepository.verify_admin(username, password)
        if not ok:
            self.set_status(401)
            return self.render("admin/login.html", title="后台登录", error=err_msg)

        self.set_auth_cookie("admin_username", username)

        # Check must_change_password
        if admin_row and admin_row["must_change_password"]:
            return self.redirect("/admin/settings?must_change=1")

        self.redirect("/admin/home")


class AdminBaseHandler(BaseHandler):
    def get_current_user(self) -> str | None:
        admin_username = self.get_secure_cookie("admin_username")
        if not admin_username:
            return None
        return admin_username.decode("utf-8")

    def prepare(self) -> None:
        if not self.current_user:
            self.redirect("/admin/login")
            return

        # RBAC: check route permission unless super admin
        path = self.request.path
        # Always-allowed routes for authenticated admins
        allowed_any = {"/admin/home", "/admin/logout", "/admin/change-password"}
        if path in allowed_any:
            return

        admin_row = AdminRepository.get_admin_by_username(self.current_user)
        if not admin_row:
            self.redirect("/admin/login")
            return

        # Super admin bypasses all checks
        if admin_row["is_super"]:
            return

        # Check if this admin's role has a menu entry for this path
        # Use regex fullmatch so dynamic routes like /admin/models/1/test
        # match the base URL /admin/models stored in menus
        allowed_urls = AdminRepository.get_admin_allowed_urls(admin_row["id"])
        if not any(re.fullmatch(pattern, path) for pattern in allowed_urls):
            self.set_status(403)
            self.finish(
                "<h3>403 · 无权限访问</h3><p>请联系超级管理员分配功能权限。</p>"
            )
            return

    def _page(self) -> int:
        try:
            return max(int(self.get_query_argument("page", "1")), 1)
        except ValueError:
            return 1

    def _message(self) -> str:
        return self.get_query_argument("msg", "")

    def _redirect_with_message(self, url: str, message: str | None) -> None:
        import urllib.parse

        encoded = urllib.parse.quote(message or "", safe="")
        self.redirect(f"{url}?msg={encoded}")


class AdminHomeHandler(AdminBaseHandler):
    def get(self) -> None:
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
    def post(self) -> None:
        self.clear_auth_cookie("admin_username")
        self.redirect("/admin/login")


class AdminRoleHandler(AdminBaseHandler):
    def get(self) -> None:
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

    def post(self) -> None:
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
    def get(self) -> None:
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

    def post(self) -> None:
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
                int(self.get_body_argument("role_id", "0") or 0),
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
            int(self.get_body_argument("role_id", "0") or 0),
            self.get_body_argument("status", "enabled"),
        )
        self._redirect_with_message("/admin/users", msg or "用户已新增" if ok else msg)


class AdminMenuHandler(AdminBaseHandler):
    def get(self) -> None:
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

    def post(self) -> None:
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
