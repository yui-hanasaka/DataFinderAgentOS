import json

from app.controllers.admin import AdminBaseHandler
from app.models.watchtower import ItemRepository, SourceRepository
from app.models.watchtower_scraper import WatchtowerScraper


class WatchtowerCollectHandler(AdminBaseHandler):
    def get(self):
        sources = SourceRepository.list_all_enabled()
        self.render(
            "admin/watchtower_collect.html",
            title="瞭望采集",
            username=self.current_user,
            sources=sources,
            msg=self._message(),
        )

    async def post(self):
        # Detect action from form body or JSON body
        content_type = (self.request.headers.get("Content-Type") or "").lower()
        if "application/json" in content_type:
            try:
                payload = json.loads(self.request.body or b"{}")
            except json.JSONDecodeError:
                self.set_status(400)
                return self.write({"error": "请求体格式错误"})
            action = payload.get("action", "search")
        else:
            action = self.get_body_argument("action", "search")

        if action == "search":
            return await self._handle_search()
        if action == "save":
            return self._handle_save(content_type)

        self.set_status(400)
        self.write({"error": "未知操作"})

    async def _handle_search(self):
        keyword = self.get_body_argument("keyword", "").strip()
        if not keyword:
            self.set_status(400)
            return self.write({"error": "请输入搜索关键词"})

        source_ids_raw = self.get_body_argument("source_ids", "")
        if not source_ids_raw:
            self.set_status(400)
            return self.write({"error": "请选择至少一个采集源"})

        try:
            source_ids = [
                int(s) for s in source_ids_raw.split(",") if s.strip().isdigit()
            ]
        except (ValueError, TypeError):
            self.set_status(400)
            return self.write({"error": "采集源参数格式错误"})

        if not source_ids:
            self.set_status(400)
            return self.write({"error": "请选择有效的采集源"})

        pages = max(1, min(10, int(self.get_body_argument("pages", "1") or 1)))
        limit = max(5, min(60, int(self.get_body_argument("limit", "15") or 15)))

        all_items = []
        for src_id in source_ids:
            source = SourceRepository.get_source(src_id)
            if not source or source["status"] != "enabled":
                continue
            try:
                items = await WatchtowerScraper.scrape_source_async(
                    src_id, keyword, pages, limit
                )
                for item in items:
                    item["source_id"] = src_id
                    item["source_name"] = source["name"]
                all_items.extend(items)
            except Exception:
                # Skip failed sources, continue with others
                pass

        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write({"ok": True, "items": all_items, "total": len(all_items)})

    def _handle_save(self, content_type: str = ""):
        if "application/json" in content_type:
            try:
                payload = json.loads(self.request.body or b"{}")
            except json.JSONDecodeError:
                self.set_status(400)
                return self.write({"error": "请求体格式错误"})
            items = payload.get("items") or []
        else:
            items_raw = self.get_body_argument("items", "")
            try:
                items = json.loads(items_raw) if items_raw else []
            except json.JSONDecodeError:
                self.set_status(400)
                return self.write({"error": "数据格式错误"})
        if not isinstance(items, list) or not items:
            self.set_status(400)
            return self.write({"error": "请选择要保存的数据"})

        saved = ItemRepository.batch_add_items(items)
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write({"ok": True, "saved": saved, "total": len(items)})
