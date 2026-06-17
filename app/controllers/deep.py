import asyncio

from tornado.ioloop import IOLoop

from app.controllers.admin import AdminBaseHandler
from app.models.deep import PER_PAGE, DeepRepository
from app.models.rate_limit import check_rate_limit


class AdminDeepHandler(AdminBaseHandler):
    def get(self) -> None:
        keyword = self.get_query_argument("keyword", "").strip()
        page = self._page()
        filter_status = self.get_query_argument("status", "")  # collected / pending

        is_deep_collected = None
        if filter_status == "collected":
            is_deep_collected = 1
        elif filter_status == "pending":
            is_deep_collected = 0

        items, total = DeepRepository.list_items_for_deep(
            keyword, page, is_deep_collected
        )

        # Get recent tasks
        from app.models.db import get_connection

        with get_connection() as conn:
            tasks = conn.execute(
                "SELECT * FROM deep_tasks ORDER BY id DESC LIMIT 10"
            ).fetchall()

        # View deep content for a specific item
        view_item_id = self.get_query_argument("view", "")
        deep_contents = []
        view_item = None
        if view_item_id and view_item_id.isdigit():
            from app.models.watchtower import ItemRepository

            view_item = ItemRepository.get_item(int(view_item_id))
            deep_contents = DeepRepository.get_deep_contents(int(view_item_id))

        self.render(
            "admin/deep.html",
            title="深度采集",
            username=self.current_user,
            items=items,
            total=total,
            page=page,
            per_page=PER_PAGE,
            keyword=keyword,
            filter_status=filter_status,
            tasks=tasks,
            view_item=view_item,
            deep_contents=deep_contents,
            msg=self._message(),
        )

    def post(self) -> None:
        action = self.get_body_argument("action", "")

        if action in ("collect", "collect_single"):
            if not check_rate_limit(f"deep_collect:{self.current_user}", 5, 300):
                self.set_status(429)
                self.write({"error": "深度采集请求过于频繁，请5分钟后再试"})
                return

        if action == "collect":
            return self._handle_collect()
        if action == "collect_single":
            return self._handle_collect_single()
        if action == "delete_task":
            return self._handle_delete_task()

        self.set_status(400)
        self.write({"error": "未知操作"})

    def _handle_collect(self) -> None:
        """Start batch deep collection for selected items."""
        item_ids_raw = self.get_body_arguments("item_ids")
        if not item_ids_raw:
            return self._redirect_with_message("/admin/deep", "请选择要深度采集的数据")

        item_ids = [int(i) for i in item_ids_raw if i.isdigit()]
        if not item_ids:
            return self._redirect_with_message("/admin/deep", "请选择有效的条目")

        task_id = DeepRepository.start_deep_collect(item_ids)
        DeepRepository.add_task_log(task_id, f"任务启动，共 {len(item_ids)} 条数据")

        # Run collection asynchronously in background
        IOLoop.current().add_callback(self._run_deep_collect, task_id, item_ids)

        return self._redirect_with_message(
            "/admin/deep",
            f"深度采集任务已启动（#{task_id}），共 {len(item_ids)} 条数据，请稍后刷新查看结果",
        )

    def _handle_collect_single(self) -> None:
        """Start single item deep collection (synchronous for immediate feedback)."""
        item_id_str = self.get_body_argument("item_id", "")
        if not item_id_str.isdigit():
            return self._redirect_with_message("/admin/deep", "无效的条目ID")

        item_id = int(item_id_str)
        task_id = DeepRepository.start_deep_collect([item_id])
        DeepRepository.add_task_log(task_id, f"单条采集启动，条目 #{item_id}")

        IOLoop.current().add_callback(self._run_deep_collect, task_id, [item_id])

        return self._redirect_with_message(
            "/admin/deep", f"深度采集已启动（#{task_id}），请稍后刷新页面查看结果"
        )

    async def _run_deep_collect(self, task_id: int, item_ids: list[int]) -> None:
        """Run deep collection in background.

        Shares a single crawl4ai browser instance across all items for
        efficiency, falling back to per-item crawler creation if the
        shared instance fails to initialise.
        """
        model = DeepRepository.get_default_model()
        completed = 0
        failed = 0

        async def _process_one(item_id: int, crawler=None) -> None:
            nonlocal completed, failed
            try:
                DeepRepository.add_task_log(task_id, f"正在采集条目 #{item_id}...")
                result = await DeepRepository.collect_single_item(
                    item_id, model, crawler
                )
                if result["ok"]:
                    DeepRepository.save_deep_result(item_id, task_id, result)
                    completed += 1
                    DeepRepository.add_task_log(
                        task_id,
                        f"条目 #{item_id} 采集成功: {result.get('title', '')[:30]}",
                    )
                else:
                    failed += 1
                    DeepRepository.add_task_log(
                        task_id,
                        f"条目 #{item_id} 采集失败: {result.get('error', '未知错误')}",
                    )
            except Exception as e:
                failed += 1
                DeepRepository.add_task_log(
                    task_id, f"条目 #{item_id} 异常: {str(e)[:100]}"
                )
            DeepRepository.update_task_progress(task_id, completed, failed)
            await asyncio.sleep(1)

        # Primary: shared crawl4ai browser for all items
        try:
            from crawl4ai import AsyncWebCrawler

            async with AsyncWebCrawler(verbose=False) as crawler:
                for item_id in item_ids:
                    await _process_one(item_id, crawler)
        except Exception as crawler_err:
            # Fallback: per-item crawler creation inside collect_single_item
            DeepRepository.add_task_log(
                task_id,
                f"共享爬虫初始化失败，降级为独立模式: {str(crawler_err)[:100]}",
            )
            for item_id in item_ids:
                await _process_one(item_id)

        if failed == 0:
            DeepRepository.complete_task(task_id)
        else:
            DeepRepository.complete_task(task_id)
            DeepRepository.add_task_log(
                task_id,
                f"采集完成: 成功 {completed} 条, 失败 {failed} 条",
            )

    def _handle_delete_task(self) -> None:
        task_id = self.get_body_argument("task_id", "")
        if not task_id.isdigit():
            return self._redirect_with_message("/admin/deep", "无效的任务ID")

        from app.models.db import get_connection

        with get_connection() as conn:
            conn.execute("DELETE FROM deep_tasks WHERE id=?", (int(task_id),))
        return self._redirect_with_message("/admin/deep", "任务已删除")
