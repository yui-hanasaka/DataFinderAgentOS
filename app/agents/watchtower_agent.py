"""
AI-driven watchtower scheduling agent.

Called by Tornado PeriodicCallback in app.py. Each tick() gathers corpus
statistics, asks the default LLM for scheduling decisions, and executes them.
"""

import json

from app.models.db import get_connection
from app.models.errors import log_error


class WatchtowerAgent:
    async def tick(self) -> None:
        try:
            stats = self._gather_stats()
            if not stats["sources"]:
                return
            decisions = await self._ai_decide(stats)
            for action in decisions:
                await self._execute_action(action)
        except Exception as exc:
            log_error("WatchtowerAgent.tick", exc)

    def _gather_stats(self) -> dict:
        with get_connection() as conn:
            sources = conn.execute(
                "SELECT id, name, source_type, fetch_interval, last_fetched"
                " FROM watchtower_sources WHERE status='enabled'"
            ).fetchall()
            source_stats = []
            for s in sources:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt,"
                    " SUM(CASE WHEN is_deep_collected=1 THEN 1 ELSE 0 END) as deep_cnt"
                    " FROM watchtower_items WHERE source_id=?",
                    (int(s["id"]),),
                ).fetchone()
                source_stats.append(
                    {
                        "id": int(s["id"]),
                        "name": s["name"],
                        "source_type": s["source_type"],
                        "fetch_interval": int(s["fetch_interval"] or 60),
                        "last_fetched": s["last_fetched"],
                        "total_items": int(row["cnt"] or 0),
                        "deep_collected": int(row["deep_cnt"] or 0),
                    }
                )
            pending = conn.execute(
                "SELECT id, title FROM watchtower_items"
                " WHERE is_deep_collected=0 ORDER BY id DESC LIMIT 10"
            ).fetchall()
        return {
            "sources": source_stats,
            "pending_deep_collect": [
                {"id": int(r["id"]), "title": r["title"]} for r in pending
            ],
        }

    async def _ai_decide(self, stats: dict) -> list[dict]:
        from app.models.model_client import chat_complete, parse_chat_response
        from app.models.model_engine import ModelRepository

        model_row = ModelRepository.get_default_model()
        if not model_row:
            return []

        system = (
            "你是数据瞭望AI调度员。根据数据源状态，以JSON数组返回调度决策。\n"
            "可用action类型:\n"
            '  {"type":"trigger_deep_collect","item_ids":[int,...]}\n'
            '  {"type":"scrape_source","source_id":int,"keyword":"..."}\n'
            '  {"type":"log_observation","message":"..."}\n'
            "只返回JSON数组，不要包含任何解释文字。"
        )
        prompt = f"当前瞭望状态:\n{json.dumps(stats, ensure_ascii=False, indent=2)}\n\n请给出调度决策:"
        try:
            api_key = str(model_row["api_key"])
            if not api_key:
                return []
            resp = await chat_complete(
                str(model_row["base_url"]),
                api_key,
                str(model_row["model_id"]),
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=400,
                stream=False,
            )
            parsed = parse_chat_response(resp.content)
            content = str(parsed.get("content", "")).strip()
            content = (
                content.removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            decisions: list[dict] = json.loads(content)
            return decisions if isinstance(decisions, list) else []
        except Exception as exc:
            log_error("WatchtowerAgent._ai_decide", exc)
            return []

    async def _execute_action(self, action: dict) -> None:
        action_type = action.get("type", "")
        try:
            match action_type:
                case "trigger_deep_collect":
                    item_ids: list[int] = [
                        int(i) for i in (action.get("item_ids") or [])[:5]
                    ]
                    if item_ids:
                        self._execute_trigger_deep_collect(item_ids)
                case "scrape_source":
                    await self._execute_scrape_source(action)
                case "log_observation":
                    self._log_decision(
                        "log_observation", str(action.get("message", "")), "logged"
                    )
        except Exception as exc:
            log_error(f"WatchtowerAgent._execute_action {action_type}", exc)

    def _execute_trigger_deep_collect(self, item_ids: list[int]) -> None:
        """实际执行深度采集：创建 deep task 并记录决策。"""
        from app.models.deep import DeepRepository

        try:
            task_id = DeepRepository.start_deep_collect(item_ids)
            self._log_decision(
                "trigger_deep_collect",
                json.dumps({"item_ids": item_ids, "task_id": task_id}),
                "executed",
            )
        except Exception as exc:
            log_error(
                f"WatchtowerAgent._execute_trigger_deep_collect item_ids={item_ids}",
                exc,
            )
            self._log_decision(
                "trigger_deep_collect",
                json.dumps(item_ids),
                f"failed: {exc}",
            )

    async def _execute_scrape_source(self, action: dict) -> None:
        """实际执行数据源抓取。"""
        from app.models.watchtower import ItemRepository, SourceRepository
        from app.models.watchtower_scraper import WatchtowerScraper

        source_id = int(action.get("source_id", 0))
        keyword = str(action.get("keyword", "") or "")
        pages = min(int(action.get("pages", 1) or 1), 3)
        limit = min(int(action.get("limit", 20) or 20), 60)

        if not source_id or not keyword:
            self._log_decision(
                "scrape_source",
                json.dumps({"source_id": source_id, "keyword": keyword}),
                "skipped: missing source_id or keyword",
            )
            return

        try:
            items = await WatchtowerScraper.scrape_source_async(
                source_id, keyword, pages, limit
            )
            saved = 0
            new_ids: list[int] = []
            if items:
                for item in items:
                    item["source_id"] = source_id
                saved, new_ids = ItemRepository.batch_add_items(items)
            SourceRepository.mark_fetched(source_id)

            # Trigger background AI analysis for newly saved items
            if new_ids:
                from app.models.watchtower import analyze_items_sentiment

                await analyze_items_sentiment(new_ids)

            self._log_decision(
                "scrape_source",
                json.dumps(
                    {
                        "source_id": source_id,
                        "keyword": keyword,
                        "pages": pages,
                        "fetched": len(items),
                        "saved": saved,
                    }
                ),
                "executed",
            )
        except Exception as exc:
            log_error(
                f"WatchtowerAgent._execute_scrape_source source_id={source_id} keyword={keyword}",
                exc,
            )
            self._log_decision(
                "scrape_source",
                json.dumps({"source_id": source_id, "keyword": keyword}),
                f"failed: {exc}",
            )

    def _log_decision(self, action: str, reason: str, outcome: str) -> None:
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO agent_decisions (source, action, outcome, reason)"
                    " VALUES (?, ?, ?, ?)",
                    ("watchtower_agent", action, outcome, reason),
                )
                conn.commit()
        except Exception as exc:
            log_error("WatchtowerAgent._log_decision", exc)
