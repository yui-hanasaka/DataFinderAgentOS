import json

from app.controllers.admin import AdminBaseHandler
from app.models.warehouse import WarehouseRepository
from app.models.watchtower import ItemRepository

PER_PAGE = 20


class AdminWarehouseHandler(AdminBaseHandler):
    """瞭望数据管理 — browse/filter/delete/export watchtower items."""

    def get(self) -> None:
        tab = self.get_query_argument("tab", "browse")
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()

        # Watchtower items with filters
        source_id = int(self.get_query_argument("source_id", "0"))
        sentiment = self.get_query_argument("sentiment", "").strip()
        risk_min = int(self.get_query_argument("risk_min", "0"))
        risk_max = int(self.get_query_argument("risk_max", "10"))
        date_from = self.get_query_argument("date_from", "").strip()
        date_to = self.get_query_argument("date_to", "").strip()
        deep_arg = self.get_query_argument("is_deep_collected", "").strip()
        is_deep_collected = None
        if deep_arg == "1":
            is_deep_collected = 1
        elif deep_arg == "0":
            is_deep_collected = 0

        items: list = []
        items_total = 0
        sources: list = []
        if tab == "browse":
            items, items_total = ItemRepository.list_items_filtered(
                keyword=keyword,
                source_id=source_id,
                sentiment=sentiment,
                risk_min=risk_min,
                risk_max=risk_max,
                is_deep_collected=is_deep_collected,
                date_from=date_from,
                date_to=date_to,
                page=page,
                per_page=PER_PAGE,
            )
            sources = ItemRepository.list_all_sources()

        # Saved queries (for sql tab)
        queries, total = (
            WarehouseRepository.list_queries(keyword, page) if tab == "sql" else ([], 0)
        )
        edit_id = self.get_query_argument("edit", "")
        edit_query = (
            WarehouseRepository.get_query(int(edit_id)) if edit_id.isdigit() else None
        )

        self.render(
            "admin/warehouse.html",
            title="瞭望数据管理",
            username=self.current_user,
            tab=tab,
            keyword=keyword,
            page=page,
            per_page=PER_PAGE,
            items=items,
            items_total=items_total,
            sources=sources,
            source_id=source_id,
            sentiment=sentiment,
            risk_min=risk_min,
            risk_max=risk_max,
            date_from=date_from,
            date_to=date_to,
            is_deep_collected=deep_arg,
            queries=queries,
            total=total,
            edit_query=edit_query,
            msg=self._message(),
        )

    def post(self) -> None:
        action = self.get_body_argument("action", "")
        q_id = self.get_body_argument("id", "")

        # Saved query CRUD
        if action == "delete_query" and q_id.isdigit():
            ok, msg = WarehouseRepository.delete_query(int(q_id))
            return self._redirect_with_message(
                "/admin/warehouse?tab=sql", msg or "已删除" if ok else msg
            )

        if action == "save_query":
            name = self.get_body_argument("name", "").strip()
            sql_query = self.get_body_argument("sql_query", "").strip()
            description = self.get_body_argument("description", "").strip()
            category = self.get_body_argument("category", "默认").strip()
            if q_id.isdigit():
                ok, msg = WarehouseRepository.update_query(
                    int(q_id),
                    {
                        "name": name,
                        "sql_query": sql_query,
                        "description": description,
                        "category": category,
                    },
                )
                return self._redirect_with_message(
                    "/admin/warehouse?tab=sql", msg or "已更新" if ok else msg
                )
            ok, msg = WarehouseRepository.create_query(
                {
                    "name": name,
                    "sql_query": sql_query,
                    "description": description,
                    "category": category,
                },
            )
            return self._redirect_with_message(
                "/admin/warehouse?tab=sql", msg or "已新增" if ok else msg
            )

        if action == "execute":
            raw_sql = self.get_body_argument("query", "").strip()
            if q_id.isdigit():
                query = WarehouseRepository.get_query(int(q_id))
                if query:
                    rows, cols, err = WarehouseRepository.execute_query(
                        query["sql_query"], trusted=True
                    )
                    self.set_header("Content-Type", "application/json")
                    if err:
                        return self.write({"error": err})
                    return self.write(
                        {"columns": cols, "rows": [list(r) for r in (rows or [])]}
                    )
                return self.write({"error": "查询不存在"})
            if raw_sql:
                rows, cols, err = WarehouseRepository.execute_query(
                    raw_sql, trusted=True
                )
                self.set_header("Content-Type", "application/json")
                if err:
                    return self.write({"error": err})
                return self.write(
                    {"columns": cols, "rows": [list(r) for r in (rows or [])]}
                )
            return self.write({"error": "请提供查询ID或SQL语句"})

        # Watchtower item operations
        if action == "delete_item" and q_id.isdigit():
            ok, msg = ItemRepository.delete_item(int(q_id))
            return self._redirect_with_message(
                "/admin/warehouse", msg or "已删除" if ok else msg
            )

        if action == "batch_delete":
            ids_str = self.get_body_argument("ids", "")
            try:
                ids = [int(x) for x in ids_str.split(",") if x.strip().isdigit()]
            except ValueError:
                return self._redirect_with_message("/admin/warehouse", "无效的ID列表")
            if not ids:
                return self._redirect_with_message(
                    "/admin/warehouse", "请选择要删除的条目"
                )
            ok, msg = ItemRepository.batch_delete_items(ids)
            return self._redirect_with_message(
                "/admin/warehouse",
                msg or f"已批量删除 {len(ids)} 条" if ok else msg,
            )

        if action == "export":
            ids_str = self.get_body_argument("ids", "")
            fmt = self.get_body_argument("format", "json")
            try:
                ids = [int(x) for x in ids_str.split(",") if x.strip().isdigit()]
            except ValueError:
                self.set_header("Content-Type", "application/json")
                return self.write({"error": "无效的ID列表"})
            rows, err = ItemRepository.export_items(ids)
            if err:
                self.set_header("Content-Type", "application/json")
                return self.write({"error": err})
            if fmt == "csv":
                self.set_header("Content-Type", "text/csv; charset=utf-8")
                self.set_header(
                    "Content-Disposition", "attachment; filename=watchtower_export.csv"
                )
                if rows:
                    headers = [k for k in rows[0].keys()]
                    self.write(",".join(headers) + "\n")
                    for r in rows:
                        self.write(
                            ",".join(
                                f'"{str(r[k] if k in r.keys() else "").replace(chr(34), chr(34) + chr(34))}"'
                                for k in headers
                            )
                            + "\n"
                        )
                return
            # JSON export
            self.set_header("Content-Type", "application/json; charset=utf-8")
            self.set_header(
                "Content-Disposition", "attachment; filename=watchtower_export.json"
            )
            return self.write(
                json.dumps([dict(r) for r in (rows or [])], ensure_ascii=False)
            )

        self._redirect_with_message("/admin/warehouse", "未知操作")
