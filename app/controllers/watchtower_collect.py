import asyncio
import json

from app.controllers.admin import AdminBaseHandler
from app.models.errors import log_error
from app.models.rate_limit import check_rate_limit
from app.models.validators import parse_int
from app.models.watchtower import (
    ItemRepository,
    SourceRepository,
    analyze_items_sentiment,
)
from app.models.watchtower_scraper import WatchtowerScraper
from app.models.model_client import chat_complete, parse_chat_response
from app.models.model_engine import ModelRepository


class WatchtowerCollectHandler(AdminBaseHandler):
    async def get(self):
        action = self.get_query_argument("action", "").strip()
        if action == "ai_search":
            return await self._handle_ai_search_sse()

        sources = SourceRepository.list_all_enabled()
        self.render(
            "admin/watchtower_collect.html",
            title="瞭望采集",
            username=self.current_user,
            sources=sources,
            msg=self._message(),
        )

    async def post(self):
        if not check_rate_limit(f"wt_collect:{self.current_user}", 5, 300):
            self.set_status(429)
            return self.write({"error": "采集请求过于频繁，请5分钟后再试"})

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
            return await self._handle_save(content_type)

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
                parse_int(s) for s in source_ids_raw.split(",") if s.strip().isdigit()
            ]
        except (ValueError, TypeError):
            self.set_status(400)
            return self.write({"error": "采集源参数格式错误"})

        if not source_ids:
            self.set_status(400)
            return self.write({"error": "请选择有效的采集源"})

        pages = parse_int(
            self.get_body_argument("pages", "1"), 1, min_value=1, max_value=10
        )
        limit = parse_int(
            self.get_body_argument("limit", "15"), 15, min_value=5, max_value=60
        )

        all_items = []
        errors: list[dict] = []

        async def _scrape_one(src_id: int) -> tuple[list, str | None]:
            source = SourceRepository.get_source(src_id)
            if not source or source["status"] != "enabled":
                return [], None
            try:
                items = await asyncio.wait_for(
                    WatchtowerScraper.scrape_source_async(
                        src_id, keyword, pages, limit
                    ),
                    timeout=25,
                )
                for item in items:
                    item["source_id"] = src_id
                    item["source_name"] = source["name"]
                if not items:
                    return (
                        [],
                        f"{source['name']}: 采集结果为空（可能遭遇反爬或选择器失效）",
                    )
                return items, None
            except asyncio.TimeoutError:
                return [], f"{source['name']}: 采集超时（>25s）"
            except Exception as e:
                log_error(f"采集源 {src_id} 抓取失败", e)
                return [], f"{source['name']}: {str(e)[:200]}"

        results = await asyncio.gather(*[_scrape_one(src_id) for src_id in source_ids])
        for items, err in results:
            all_items.extend(items)
            if err:
                errors.append({"msg": err})

        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write(
            {"ok": True, "items": all_items, "total": len(all_items), "errors": errors}
        )

    async def _handle_save(self, content_type: str = ""):
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

        # Normalize scraper field names to DB column names
        # Scraper returns: snippet, published_time, source
        # DB expects:      content, published_at
        normalized: list[dict] = []
        for item in items:
            entry: dict[str, object] = {
                "source_id": item.get("source_id", 0),
                "title": item.get("title", ""),
                "content": item.get("snippet") or item.get("content") or "",
                "url": item.get("url") or "",
                "published_at": item.get("published_time")
                or item.get("published_at")
                or "",
                "keywords": item.get("keywords", "[]"),
                "raw_json": item.get("raw_json", "{}"),
                "source_name": item.get("source_name", ""),
            }
            normalized.append(entry)

        saved, new_ids = ItemRepository.batch_add_items(normalized)

        # Mark sources as fetched
        source_ids_seen: set[int] = set()
        for item in items:
            src_id = item.get("source_id")
            if src_id is not None:
                sid = int(src_id)
                if sid not in source_ids_seen:
                    source_ids_seen.add(sid)
                    try:
                        SourceRepository.mark_fetched(sid)
                    except Exception as e:
                        log_error(f"mark_fetched source_id={sid}", e)

        # Trigger background AI analysis for newly inserted items
        if new_ids:
            asyncio.create_task(analyze_items_sentiment(new_ids))

        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write({"ok": True, "saved": saved, "total": len(items)})

    async def _handle_ai_search_sse(self):
        self.set_header("Content-Type", "text/event-stream; charset=utf-8")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Connection", "keep-alive")

        desc = self.get_query_argument("desc", "").strip()
        if not desc:
            self.write(f"data: {json.dumps({'type': 'error', 'message': '请输入需求描述'})}\n\n")
            await self.flush()
            return

        source_ids_raw = self.get_query_argument("source_ids", "")
        source_ids = []
        if source_ids_raw:
            source_ids = [int(x) for x in source_ids_raw.split(",") if x.strip().isdigit()]
        if not source_ids:
            source_ids = [src["id"] for src in SourceRepository.list_all_enabled()]

        if not source_ids:
            self.write(f"data: {json.dumps({'type': 'error', 'message': '没有可用的采集源'})}\n\n")
            await self.flush()
            return

        model_row = ModelRepository.get_default_model()
        if not model_row or not model_row.get("api_key"):
            self.write(f"data: {json.dumps({'type': 'error', 'message': '未配置默认模型或API Key'})}\n\n")
            await self.flush()
            return

        # 1. Generate keywords
        keywords = desc
        try:
            prompt = (
                "你是一个智能搜索助手。用户给你一个想要收集的信息的描述，请提炼并生成最适合在搜索引擎或新闻网站上查询的中文或英文关键词。\n"
                "要求：仅返回1-3个关键词，用空格分隔，不要有任何多余标点、解释或引导词（如'关键词：'）。\n\n"
                f"用户描述：{desc}"
            )
            resp = await chat_complete(
                model_row["base_url"],
                model_row["api_key"],
                model_row["model_id"],
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=60,
                stream=False,
            )
            raw = await resp.aread()
            parsed = parse_chat_response(raw)
            keywords = str(parsed.get("content", "")).strip()
            if keywords.startswith("```"):
                keywords = keywords.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        except Exception as e:
            log_error("AI Search initial keywords generation failed", e)
            keywords = desc

        max_iterations = 3
        all_collected_items = []

        async def _scrape_one(src_id: int, kw: str) -> list:
            source = SourceRepository.get_source(src_id)
            if not source or source["status"] != "enabled":
                return []
            try:
                items = await asyncio.wait_for(
                    WatchtowerScraper.scrape_source_async(
                        src_id, kw, 1, 10
                    ),
                    timeout=15,
                )
                for item in items:
                    item["source_id"] = src_id
                    item["source_name"] = source["name"]
                return items
            except Exception as ex:
                log_error(f"AI Search scrape failed src={src_id} kw={kw}", ex)
                return []

        for iteration in range(1, max_iterations + 1):
            self.write(f"data: {json.dumps({'type': 'iteration_start', 'iteration': iteration, 'keywords': keywords})}\n\n")
            await self.flush()

            # Scrape in parallel
            scrape_tasks = [_scrape_one(sid, keywords) for sid in source_ids]
            results = await asyncio.gather(*scrape_tasks)

            round_items = []
            for res_list in results:
                round_items.extend(res_list)

            # De-duplicate by URL
            unique_round_items = []
            seen_urls = {item["url"] for item in all_collected_items if item.get("url")}
            for item in round_items:
                url = item.get("url")
                if not url or url not in seen_urls:
                    unique_round_items.append(item)
                    if url:
                        seen_urls.add(url)

            all_collected_items.extend(unique_round_items)

            self.write(f"data: {json.dumps({'type': 'results', 'iteration': iteration, 'keywords': keywords, 'items': unique_round_items})}\n\n")
            await self.flush()

            if len(unique_round_items) >= 5 or iteration == max_iterations:
                break

            # Refine keywords for next round
            try:
                refine_prompt = (
                    f"你是一个智能搜索助手。用户期望收集的信息是「{desc}」。\n"
                    f"前一轮使用的关键词是「{keywords}」，共采集到 {len(unique_round_items)} 条有用结果，数量偏少或不够精准。\n"
                    "请结合当前轮次的结果，重新生成一组新的更精准或者略微宽泛的关键词来拓宽搜索面。\n"
                    "要求：仅返回1-3个关键词，用空格分隔，不要有任何多余标点、解释或引导词。\n"
                )
                resp = await chat_complete(
                    model_row["base_url"],
                    model_row["api_key"],
                    model_row["model_id"],
                    [{"role": "user", "content": refine_prompt}],
                    temperature=0.3,
                    max_tokens=60,
                    stream=False,
                )
                raw = await resp.aread()
                parsed = parse_chat_response(raw)
                new_kw = str(parsed.get("content", "")).strip()
                if new_kw.startswith("```"):
                    new_kw = new_kw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                if new_kw and new_kw != keywords:
                    keywords = new_kw
            except Exception as e:
                log_error("AI Search keywords refinement failed", e)
                break

        self.write(f"data: {json.dumps({'type': 'done', 'total': len(all_collected_items)})}\n\n")
        await self.flush()
