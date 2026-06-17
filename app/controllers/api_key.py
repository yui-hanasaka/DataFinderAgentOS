from app.controllers.admin import AdminBaseHandler
from app.models.api_key import ApiKeyRepository
from app.models.rate_limit import check_rate_limit
from app.models.secrets_store import mask

PER_PAGE = 20


class AdminApiKeyHandler(AdminBaseHandler):
    def get(self) -> None:
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        api_keys, total = ApiKeyRepository.list_keys(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_api = None
        if edit_id.isdigit():
            row = ApiKeyRepository.get_key(int(edit_id))
            if row:
                edit_api = dict(row)
                edit_api["api_key"] = mask(edit_api.get("api_key") or "")
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

    def post(self) -> None:
        if not check_rate_limit(f"api_key:{self.current_user}", 20, 60):
            self.set_status(429)
            self.write({"error": "操作过于频繁，请稍后再试"})
            return

        action = self.get_body_argument("action", "")
        api_id = self.get_body_argument("id", "")
        if action == "delete" and api_id.isdigit():
            ApiKeyRepository.delete_key(int(api_id))
            return self._redirect_with_message("/admin/apis", "已删除")
        name = self.get_body_argument("name", "").strip()
        api_type = self.get_body_argument("api_type", "other")
        endpoint = self.get_body_argument("endpoint", "").strip()
        api_key_val = self.get_body_argument("api_key", "").strip()
        status = self.get_body_argument("status", "enabled")
        data: dict[str, object] = {
            "name": name,
            "api_type": api_type,
            "endpoint": endpoint,
            "api_key": api_key_val,
            "status": status,
        }
        if api_id.isdigit():
            ApiKeyRepository.update_key(int(api_id), data)
            return self._redirect_with_message("/admin/apis", "已更新")
        ApiKeyRepository.create_key(data)
        self._redirect_with_message("/admin/apis", "已新增")
