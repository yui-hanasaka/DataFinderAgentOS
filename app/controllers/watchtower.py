from app.controllers.admin import AdminBaseHandler
from app.models.rate_limit import check_rate_limit
from app.models.validators import parse_int
from app.models.watchtower import ItemRepository, SourceRepository

PER_PAGE = 20


class AdminWatchtowerHandler(AdminBaseHandler):
    def get(self) -> None:
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        sources, src_total = SourceRepository.list_sources(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_source = (
            SourceRepository.get_source(parse_int(edit_id))
            if edit_id.isdigit()
            else None
        )
        recent_items = ItemRepository.recent_items(10)
        self.render(
            "admin/watchtower.html",
            title="瞭望管理",
            username=self.current_user,
            sources=sources,
            src_total=src_total,
            src_page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            edit_source=edit_source,
            recent_items=recent_items,
            msg=self._message(),
        )

    def post(self) -> None:
        if not check_rate_limit(f"admin_watchtower:{self.current_user}", 15, 60):
            self.set_status(429)
            return self._redirect_with_message(
                "/admin/watchtower", "请求过于频繁，请稍后再试"
            )

        action = self.get_body_argument("action", "")
        src_id = self.get_body_argument("id", "")
        if action == "delete" and src_id.isdigit():
            ok, msg = SourceRepository.delete_source(parse_int(src_id))
            return self._redirect_with_message(
                "/admin/watchtower", msg or "已删除" if ok else msg
            )
        name = self.get_body_argument("name", "").strip()
        source_type = self.get_body_argument("source_type", "rss")
        url = self.get_body_argument("url", "").strip()
        fetch_interval = parse_int(
            self.get_body_argument("fetch_interval", "60"), 60, min_value=1
        )
        status = self.get_body_argument("status", "enabled")
        url_template = self.get_body_argument("url_template", "").strip()
        request_headers = self.get_body_argument("request_headers", "").strip()
        config_json = self.get_body_argument("config_json", "{}").strip()
        if src_id.isdigit():
            ok, msg = SourceRepository.update_source(
                parse_int(src_id),
                name,
                source_type,
                url,
                fetch_interval,
                status,
                url_template,
                request_headers,
                config_json,
            )
            return self._redirect_with_message(
                "/admin/watchtower", msg or "已更新" if ok else msg
            )
        ok, msg = SourceRepository.create_source(
            name,
            source_type,
            url,
            fetch_interval,
            status,
            url_template,
            request_headers,
            config_json,
        )
        self._redirect_with_message("/admin/watchtower", msg or "已新增" if ok else msg)
