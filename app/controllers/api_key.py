from app.controllers.admin import AdminBaseHandler
from app.models.db import get_connection

PER_PAGE = 20


class AdminApiKeyHandler(AdminBaseHandler):
    def get(self):
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        where = "WHERE name LIKE ? OR api_type LIKE ?" if keyword else ""
        params = [f"%{keyword}%", f"%{keyword}%"] if keyword else []
        with get_connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM api_keys {where}", params
            ).fetchone()[0]
            offset = (max(page, 1) - 1) * PER_PAGE
            api_keys = conn.execute(
                f"SELECT * FROM api_keys {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                params + [PER_PAGE, offset],
            ).fetchall()
        edit_id = self.get_query_argument("edit", "")
        edit_api = None
        if edit_id.isdigit():
            with get_connection() as conn:
                edit_api = conn.execute(
                    "SELECT * FROM api_keys WHERE id=?", (int(edit_id),)
                ).fetchone()
        self.render(
            "admin/apis.html",
            title="接口管理",
            username=self.current_user,
            api_keys=api_keys,
            total=total,
            page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            edit_api=edit_api,
            msg=self._message(),
        )

    def post(self):
        action = self.get_body_argument("action", "")
        api_id = self.get_body_argument("id", "")
        if action == "delete" and api_id.isdigit():
            with get_connection() as conn:
                conn.execute("DELETE FROM api_keys WHERE id=?", (int(api_id),))
            return self._redirect_with_message("/admin/apis", "已删除")
        name = self.get_body_argument("name", "").strip()
        api_type = self.get_body_argument("api_type", "other")
        endpoint = self.get_body_argument("endpoint", "").strip()
        api_key_val = self.get_body_argument("api_key", "").strip()
        status = self.get_body_argument("status", "enabled")
        if api_id.isdigit():
            with get_connection() as conn:
                conn.execute(
                    "UPDATE api_keys SET name=?,api_type=?,endpoint=?,api_key=?,status=?,updated_at=datetime('now') WHERE id=?",
                    (name, api_type, endpoint, api_key_val, status, int(api_id)),
                )
            return self._redirect_with_message("/admin/apis", "已更新")
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO api_keys(name, api_type, endpoint, api_key, status) VALUES(?,?,?,?,?)",
                (name, api_type, endpoint, api_key_val, status),
            )
        self._redirect_with_message("/admin/apis", "已新增")
