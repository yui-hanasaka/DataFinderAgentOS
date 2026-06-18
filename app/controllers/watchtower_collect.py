import asyncio
import json

from app.agents import agent_loop
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

        desc = self.get_query_argument("desc", "").strip()
        if not desc:
            self.write(
                f"data: {json.dumps({'type': 'error', 'message': '请输入需求描述'})}\n\n"
            )
            await self.flush()
            return

        if not check_rate_limit(f"wt_ai_search:{self.current_user}", 3, 300):
            self.set_status(429)
            self.write(
                f"data: {json.dumps({'type': 'error', 'message': 'AI 采集请求过于频繁，请5分钟后再试'})}\n\n"
            )
            await self.flush()
            return

        model_row = ModelRepository.get_default_model()
        if not model_row or not model_row.get("api_key"):
            self.write(
                f"data: {json.dumps({'type': 'error', 'message': '未配置默认模型或API Key'})}\n\n"
            )
            await self.flush()
            return

        # Build sources info for AI reference
        sources = SourceRepository.list_all_enabled()
        sources_info = ", ".join(f"{s['name']}({s['source_type']})" for s in sources)

        system_prompt = (
            "你是数据瞭望采集智能代理（Watchtower Collect Agent）。"
            "你的任务是根据用户的信息需求，自主搜索互联网，评估每条结果的相关性，"
            "将有价值的信息保存到瞭望数据库，并迭代优化搜索策略直到获得满意的结果。\n"
            "\n"
            "## 工作流程\n"
            "1. **规划搜索**：理解用户需求，生成合适的中文关键词，使用 web_search 进行搜索\n"
            "2. **评估结果**：仔细阅读每条搜索结果的标题和摘要，判断是否与用户需求相关\n"
            "3. **保存相关数据**：对确实相关的结果，使用 watchtower_insert 保存\n"
            "4. **深入采集**：对特别有价值的链接，使用 deep_collect 进行深度分析\n"
            "5. **迭代优化**：根据已获得的结果质量和数量，调整关键词继续搜索，扩大覆盖面\n"
            "6. **自主停止**：当获得足够多的高质量结果（建议10条以上），"
            "或连续尝试多组关键词后无新发现时，主动停止并总结\n"
            "\n"
            "## 相关性判断标准\n"
            "- **必须保存**：内容直接匹配用户需求，信息丰富，有具体事实/数据/观点\n"
            "- **不应保存**：\n"
            "  - ICP备案页面、隐私政策、Cookie声明、用户协议、服务条款\n"
            "  - 网站导航页、404错误页、空白页、纯广告页\n"
            "  - 与用户需求完全无关的内容\n"
            "  - 内容过于简短（少于50字）且无实质信息\n"
            "  - 纯搜索引擎结果聚合页（无原创内容）\n"
            "- **有疑问时**：倾向于保存，宁可多存不可漏掉\n"
            "\n"
            "## watchtower_insert 使用说明\n"
            "- title: 资讯标题（必填）\n"
            "- content: 资讯正文或摘要（必填，至少50字）\n"
            "- url: 来源链接（强烈建议提供，用于URL去重）\n"
            "- source_name: 来源名称，如 'AI采集-<平台名>'\n"
            "- sentiment: 情感倾向，可选 positive/negative/neutral\n"
            "- 同URL不会重复插入，返回 action: 'skipped_duplicate'\n"
            "\n"
            "## 搜索策略\n"
            "- 优先使用 web_search（通过Bing/DuckDuckGo搜索）\n"
            "- 如果 web_search 返回空，立即使用 code_execute 编写Python爬虫直接搜索\n"
            "- 每组关键词搜索后，评估结果质量，调整关键词角度再搜\n"
            "- 覆盖不同角度：如搜'政策'也搜'法规''文件''通知'\n"
            "- 对特别重要的链接使用 deep_collect 进行AI摘要\n"
            "\n"
            "## 停止条件\n"
            "- 已保存10条以上高质量相关结果 → 总结并停止\n"
            "- 已尝试3组以上不同关键词且最新一组无新发现 → 总结并停止\n"
            "- 工具调用轮次达到上限 → 自然结束\n"
            "\n"
            "## 输出要求\n"
            "- 每次搜索后必须口头评估结果质量（相关性、信息量）\n"
            "- 每次保存后简要说明为什么这条值得保存\n"
            "- 停止前给出最终总结：共搜索了多少次、保存了多少条、覆盖了哪些角度\n"
            f"\n可用的采集源（仅供了解，实际的网络搜索不受此限制）：{sources_info}"
        )

        messages: list[dict[str, object]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户信息需求：{desc}\n请开始采集。"},
        ]

        allowed_tools = [
            "web_search",
            "web_fetch",
            "code_execute",
            "watchtower_insert",
            "watchtower_search",
            "deep_collect",
        ]

        saved_items: list[dict[str, object]] = []
        full_text_parts: list[str] = []

        async def _sse(event_type: str, data: object) -> None:
            nonlocal saved_items, full_text_parts
            if event_type == "text":
                full_text_parts.append(str(data))
                payload = json.dumps({"type": "text", "content": str(data)})
            elif isinstance(data, dict):
                payload = json.dumps({"type": event_type, **data})
                # Track watchtower_insert results for final summary
                if (
                    event_type == "tool_result"
                    and data.get("name") == "watchtower_insert"
                ):
                    try:
                        result = json.loads(str(data.get("content", "{}")))
                        if result.get("ok") and result.get("title"):
                            saved_items.append(
                                {
                                    "title": result.get("title", ""),
                                    "url": result.get("url", ""),
                                    "action": result.get("action", "created"),
                                }
                            )
                    except (json.JSONDecodeError, TypeError):
                        pass
            else:
                payload = json.dumps({"type": event_type, "data": str(data)})
            try:
                self.write(f"data: {payload}\n\n")
                await self.flush()
            except Exception:
                pass

        try:
            await agent_loop.run(
                desc,
                messages,
                model_row,
                _sse,
                allowed_tools=allowed_tools,
            )
        except Exception as e:
            log_error("WatchtowerCollectHandler agent_loop", e)
            self.write(
                f"data: {json.dumps({'type': 'error', 'message': f'AI 采集执行失败: {e}'})}\n\n"
            )
            await self.flush()
            return

        self.write(
            f"data: {json.dumps({'type': 'done', 'total_saved': len(saved_items), 'saved_items': saved_items, 'full_text': ''.join(full_text_parts)})}\n\n"
        )
        self.write("data: [DONE]\n\n")
        await self.flush()
