from app.controllers.admin import AdminBaseHandler
from app.models.watchtower import SourceRepository, ItemRepository

PER_PAGE = 20

class AdminWatchtowerHandler(AdminBaseHandler):
    def get(self):
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        sources, src_total = SourceRepository.list_sources(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_source = SourceRepository.get_source(int(edit_id)) if edit_id.isdigit() else None
        recent_items = ItemRepository.recent_items(10)
        self.render("admin/watchtower.html", title="瞭望管理", username=self.current_user,
                    sources=sources, src_total=src_total, src_page=page, per_page=PER_PAGE,
                    keyword=keyword, edit_source=edit_source, recent_items=recent_items,
                    msg=self._message())

    def post(self):
        action = self.get_body_argument("action", "")
        src_id = self.get_body_argument("id", "")
        if action == "delete" and src_id.isdigit():
            ok, msg = SourceRepository.delete_source(int(src_id))
            return self._redirect_with_message("/admin/watchtower", msg or "已删除" if ok else msg)
        name = self.get_body_argument("name", "").strip()
        source_type = self.get_body_argument("source_type", "rss")
        url = self.get_body_argument("url", "").strip()
        fetch_interval = int(self.get_body_argument("fetch_interval", "60") or 60)
        status = self.get_body_argument("status", "enabled")
        if src_id.isdigit():
            ok, msg = SourceRepository.update_source(int(src_id), name, source_type, url, fetch_interval, status)
            return self._redirect_with_message("/admin/watchtower", msg or "已更新" if ok else msg)
        ok, msg = SourceRepository.create_source(name, source_type, url, fetch_interval, status)
        self._redirect_with_message("/admin/watchtower", msg or "已新增" if ok else msg)
