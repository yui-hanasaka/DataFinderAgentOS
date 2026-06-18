from app.controllers.admin import AdminBaseHandler
from app.models.warehouse import WarehouseRepository
from app.models.watchtower import ItemRepository

PER_PAGE = 20


class AdminWarehouseHandler(AdminBaseHandler):
    def get(self) -> None:
        tab = self.get_query_argument("tab", "queries")
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()

        queries, total = WarehouseRepository.list_queries(keyword, page)
        edit_id = self.get_query_argument("edit", "")
        edit_query = (
            WarehouseRepository.get_query(int(edit_id)) if edit_id.isdigit() else None
        )

        items: list = []
        items_total = 0
        if tab == "browse":
            items, items_total = ItemRepository.list_items(keyword, page)

        self.render(
            "admin/warehouse.html",
            title="数据仓库",
            username=self.current_user,
            tab=tab,
            queries=queries,
            total=total,
            page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            edit_query=edit_query,
            items=items,
            items_total=items_total,
            msg=self._message(),
        )

    def post(self) -> None:
        action = self.get_body_argument("action", "")
        q_id = self.get_body_argument("id", "")
        if action == "delete" and q_id.isdigit():
            ok, msg = WarehouseRepository.delete_query(int(q_id))
            return self._redirect_with_message(
                "/admin/warehouse", msg or "已删除" if ok else msg
            )
        if action == "delete_item" and q_id.isdigit():
            ok, msg = ItemRepository.delete_item(int(q_id))
            return self._redirect_with_message(
                "/admin/warehouse?tab=browse", msg or "已删除" if ok else msg
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
                "/admin/warehouse", msg or "已更新" if ok else msg
            )
        ok, msg = WarehouseRepository.create_query(
            {
                "name": name,
                "sql_query": sql_query,
                "description": description,
                "category": category,
            },
        )
        self._redirect_with_message("/admin/warehouse", msg or "已新增" if ok else msg)
