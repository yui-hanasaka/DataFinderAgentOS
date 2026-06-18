import json
import re
from datetime import datetime

from app.models.db import get_connection
from app.models.errors import log_error
from app.models.model_client import chat_complete, parse_chat_response
from app.models.model_engine import ModelRepository


PER_PAGE = 20


def _extract_json_from_model_output(text: str) -> str:
    """Extract and repair JSON from model output.

    Handles:
    - Markdown code blocks (```json ... ``` or ``` ... ```)
    - Leading/trailing non-JSON text
    - Truncated JSON (closes unclosed strings and braces)
    """
    text = text.strip()

    # Strip markdown code blocks — try fenced block first
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    # Try to find JSON object boundaries if there's extra text
    first_brace = text.find("{")
    if first_brace > 0:
        text = text[first_brace:]
    last_brace = text.rfind("}")
    if last_brace >= 0 and last_brace < len(text) - 1:
        text = text[: last_brace + 1]

    # If already valid, return as-is
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Repair truncated JSON: close unclosed strings, arrays, and objects
    repaired = _repair_truncated_json(text)
    return repaired


def _repair_truncated_json(text: str) -> str:
    """Best-effort repair of truncated JSON.

    - Closes unclosed strings
    - Closes unclosed arrays
    - Closes unclosed objects
    """
    result = text.rstrip()
    if not result:
        return "{}"

    # Stack of open delimiters
    stack: list[str] = []
    in_string = False
    escape_next = False

    for ch in result:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()

    # If we're still inside a string, close it
    if in_string:
        result += '"'

    # Close remaining open delimiters in reverse order
    for opener in reversed(stack):
        closer = "}" if opener == "{" else "]"
        result += closer

    return result


class DeepRepository:
    @staticmethod
    def list_items_for_deep(
        keyword: str = "",
        page: int = 1,
        is_deep_collected: int | None = None,
    ):
        """List watchtower items available for deep collection."""
        per_page = PER_PAGE
        offset = (max(page, 1) - 1) * per_page
        like = f"%{keyword}%"

        where = "WHERE (i.title LIKE ? OR i.url LIKE ?)"
        params: list = [like, like]
        if is_deep_collected is not None:
            where += " AND i.is_deep_collected = ?"
            params.append(is_deep_collected)

        with get_connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM watchtower_items i {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""SELECT i.*, s.name AS source_name,
                    (SELECT COUNT(*) FROM deep_contents dc WHERE dc.item_id = i.id) AS deep_count
                    FROM watchtower_items i
                    LEFT JOIN watchtower_sources s ON i.source_id = s.id
                    {where}
                    ORDER BY i.id DESC LIMIT ? OFFSET ?""",
                params + [per_page, offset],
            ).fetchall()
        return rows, total

    @staticmethod
    def start_deep_collect(item_ids: list[int]) -> int:
        """Start a deep collection task for the given items. Returns task_id."""
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO deep_tasks(name, target_url, depth, status,
                   target_item_ids, total_items, progress, started_at)
                   VALUES(?, ?, 1, 'running', ?, ?, 0, datetime('now'))""",
                (
                    f"深度采集任务 {datetime.now().strftime('%m-%d %H:%M')}",
                    "",
                    json.dumps(item_ids),
                    len(item_ids),
                ),
            )
            return cur.lastrowid or 0

    @staticmethod
    def get_default_model():
        """Get the default model from model engine."""
        return ModelRepository.get_default_model()

    @staticmethod
    async def collect_single_item(
        item_id: int, model: dict | None, crawler=None
    ) -> dict:
        """Deep collect a single item: scrape content, summarize with model.

        Args:
            item_id: The watchtower item ID to collect.
            model: The AI model config dict (base_url, api_key, model_id).
            crawler: Optional shared crawl4ai AsyncWebCrawler instance.
                     When doing batch collection, pass a single crawler to
                     avoid per-item browser startup overhead.

        Returns result dict with keys: ok, title, url, markdown, plain_text, summary.
        """
        from app.models.watchtower import ItemRepository

        item = ItemRepository.get_item(item_id)
        if not item:
            return {"ok": False, "error": "条目不存在"}

        result = {
            "ok": False,
            "item_id": item_id,
            "title": item["title"] or "",
            "url": item["url"] or "",
            "markdown": "",
            "plain_text": "",
            "summary": "",
            "keywords": "[]",
            "sentiment": "",
            "risk": 0,
        }

        # Step 1: Scrape the URL for content (crawl4ai → requests+BS4 fallback)
        content_text = item["content"] or ""
        if item["url"] and item["url"].startswith("http"):
            # Primary: crawl4ai — handles JS rendering, anti-bot, produces clean markdown
            try:
                from crawl4ai import AsyncWebCrawler

                async def _crawl_with(crw) -> str:
                    result = await crw.arun(url=item["url"])
                    if result and result.markdown:
                        return result.markdown[:8000]
                    return ""

                if crawler is not None:
                    content_text = await _crawl_with(crawler) or content_text
                else:
                    async with AsyncWebCrawler(verbose=False) as fresh:
                        content_text = await _crawl_with(fresh) or content_text
            except Exception as e:
                log_error(
                    f"DeepRepository crawl4ai failed item_id={item_id} url={item['url']}",
                    e,
                )

            # Fallback: requests + BeautifulSoup for sites crawl4ai cannot handle
            if not content_text:
                try:
                    from tornado.ioloop import IOLoop

                    import requests
                    from bs4 import BeautifulSoup

                    def _fetch():
                        resp = requests.get(
                            item["url"],
                            headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                            },
                            timeout=15,
                        )
                        soup = BeautifulSoup(resp.content, "html.parser")
                        for tag in soup(["script", "style", "nav", "footer", "header"]):
                            tag.decompose()
                        return soup.get_text(separator="\n", strip=True)[:8000]

                    content_text = await IOLoop.current().run_in_executor(None, _fetch)
                except Exception as e:
                    log_error(
                        f"DeepRepository fallback fetch failed item_id={item_id} url={item['url']}",
                        e,
                    )

        if not content_text:
            result["ok"] = True
            result["plain_text"] = item["content"] or "(无内容)"
            return result

        result["plain_text"] = content_text[:5000]

        # Step 2: Use model to summarize if available
        if model:
            try:
                summary = await DeepRepository._summarize_with_model(
                    model, item["title"] or "", content_text[:4000]
                )
                result["summary"] = summary.get("summary", "")
                result["keywords"] = json.dumps(
                    summary.get("keywords", []), ensure_ascii=False
                )
                result["sentiment"] = summary.get("sentiment", "")
                result["risk"] = summary.get("risk", 0)
                result["markdown"] = summary.get("markdown", "")
            except Exception as e:
                log_error(
                    f"DeepRepository.collect_single_item summarize item_id={item_id} title={item['title'] or ''}",
                    e,
                )
                result["summary"] = content_text[:500]

        result["ok"] = True
        return result

    @staticmethod
    async def _summarize_with_model(model: dict, title: str, content: str) -> dict:
        """Use the model to summarize and analyze content.

        Returns a dict with keys: summary, keywords, sentiment, risk, markdown.
        On any failure returns a safe fallback (never raises).
        """
        prompt = f"""请分析以下文章内容并以纯JSON格式返回（不要用```json包裹，直接返回JSON对象）：
标题：{title}
内容：{content[:3000]}

严格返回此JSON结构（summary不超过200字，markdown不超过500字）：
{{
    "summary": "200字以内的中文摘要",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "sentiment": "positive/negative/neutral",
    "risk": 0,
    "markdown": "精简的markdown格式内容，不超过500字"
}}"""

        messages = [
            {
                "role": "system",
                "content": "你是一个专业的内容分析助手。必须严格返回纯JSON对象，不要包含任何markdown标记或额外说明文字。确保JSON中的字符串值内不包含未转义的双引号。",
            },
            {"role": "user", "content": prompt},
        ]

        content_str = ""
        try:
            resp = await chat_complete(
                model["base_url"],
                model["api_key"],
                model["model_id"],
                messages,
                temperature=0.3,
                max_tokens=4096,
                stream=False,
            )
            raw = await resp.aread()
            parsed = parse_chat_response(raw)
            content_str = str(parsed.get("content", "{}"))

            # Extract and repair JSON from model output
            cleaned = _extract_json_from_model_output(content_str)
            result: dict = json.loads(cleaned)

            # Validate and sanitize result fields
            return {
                "summary": str(result.get("summary", ""))[:500],
                "keywords": (
                    list(result.get("keywords", []))
                    if isinstance(result.get("keywords"), list)
                    else []
                )[:10],
                "sentiment": str(result.get("sentiment", "neutral")),
                "risk": (
                    int(result.get("risk", 0))
                    if isinstance(result.get("risk"), (int, float))
                    else 0
                ),
                "markdown": str(result.get("markdown", ""))[:5000],
            }
        except Exception as e:
            log_error(
                f"DeepRepository._summarize_with_model json_parse title={title} content_preview={content_str[:200]}",
                e,
            )
            return {
                "summary": content[:200],
                "keywords": [],
                "sentiment": "neutral",
                "risk": 0,
                "markdown": content[:2000],
            }

    @staticmethod
    def save_deep_result(item_id: int, task_id: int | None, result: dict) -> None:
        """Save deep collection result to deep_contents and update item status."""
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO deep_contents(item_id, task_id, title, url,
                   markdown, plain_text, summary, keywords, sentiment, risk)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    item_id,
                    task_id,
                    result.get("title", ""),
                    result.get("url", ""),
                    result.get("markdown", ""),
                    result.get("plain_text", ""),
                    result.get("summary", ""),
                    result.get("keywords", "[]"),
                    result.get("sentiment", ""),
                    result.get("risk", 0),
                ),
            )
            conn.execute(
                """UPDATE watchtower_items SET is_deep_collected=1,
                   deep_collected_at=datetime('now') WHERE id=?""",
                (item_id,),
            )

    @staticmethod
    def update_task_progress(task_id: int, completed: int, failed: int) -> None:
        """Update task progress counters.

        Calculates progress in Python because SQLite column references
        inside an UPDATE always resolve to the pre-update value — the old
        ``CAST((completed_items / total_items) * 100 AS INTEGER)``
        expression was reading the *previous* completed_items, not the
        value just written, causing progress to lag by one step.
        """
        with get_connection() as conn:
            row = conn.execute(
                "SELECT total_items FROM deep_tasks WHERE id=?", (task_id,)
            ).fetchone()
            total = row["total_items"] if row else 0
            processed = completed + failed
            progress = int(processed / max(total, 1) * 100) if total > 0 else 0
            conn.execute(
                "UPDATE deep_tasks SET completed_items=?, failed_items=?, progress=? WHERE id=?",
                (completed, failed, progress, task_id),
            )

    @staticmethod
    def complete_task(task_id: int) -> None:
        """Mark a task as completed."""
        with get_connection() as conn:
            conn.execute(
                "UPDATE deep_tasks SET status='completed', finished_at=datetime('now') WHERE id=?",
                (task_id,),
            )

    @staticmethod
    def fail_task(task_id: int, error: str) -> None:
        """Mark a task as failed."""
        with get_connection() as conn:
            conn.execute(
                """UPDATE deep_tasks SET status='failed', error_message=?,
                   finished_at=datetime('now') WHERE id=?""",
                (error, task_id),
            )

    @staticmethod
    def get_deep_contents(item_id: int) -> list:
        """Get deep collection contents for an item."""
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM deep_contents WHERE item_id=? ORDER BY id DESC",
                (item_id,),
            ).fetchall()

    @staticmethod
    def get_task_logs(task_id: int) -> list[str]:
        """Get task logs."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT logs FROM deep_tasks WHERE id=?", (task_id,)
            ).fetchone()
        if row and row["logs"]:
            try:
                return json.loads(row["logs"])
            except json.JSONDecodeError:
                return []
        return []

    @staticmethod
    def add_task_log(task_id: int, message: str) -> None:
        """Add a log entry to a task.

        The read and write happen inside a single connection to avoid the
        read-modify-write race that existed when get_task_logs() opened its
        own connection separately.  Within Tornado's single-threaded event
        loop and SQLite's serialized-writes model this is safe; if the app
        ever moves to a multi-worker or WAL+multi-thread setup the log array
        should be moved to a dedicated deep_task_logs table instead.
        """
        timestamped = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        with get_connection() as conn:
            row = conn.execute(
                "SELECT logs FROM deep_tasks WHERE id=?", (task_id,)
            ).fetchone()
            logs: list[str] = []
            if row and row["logs"]:
                try:
                    logs = json.loads(row["logs"])
                except json.JSONDecodeError:
                    logs = []
            logs.append(timestamped)
            conn.execute(
                "UPDATE deep_tasks SET logs=? WHERE id=?",
                (json.dumps(logs, ensure_ascii=False), task_id),
            )


async def run_deep_collect_task(task_id: int, item_ids: list[int]) -> None:
    """Standalone coroutine for running a deep collection task.

    Extracted from AdminDeepHandler so both the HTTP handler and the
    WatchtowerAgent can schedule it via IOLoop.add_callback / create_task
    without depending on the handler class.

    Uses ConcurrentExecutor from app.agents.concurrent_executor to process
    items in parallel.  Shares a single crawl4ai browser across all items
    for efficiency; falls back to per-item (no-crawler) mode if crawl4ai is
    unavailable or fails to initialise.  Each item's failure is isolated —
    a crash on one item never aborts the rest of the batch.
    """
    from app.agents.concurrent_executor import ConcurrentExecutor
    import asyncio as _asyncio

    model = DeepRepository.get_default_model()
    completed = 0
    failed = 0
    lock = _asyncio.Lock()

    async def _process_one(item_id: int, crawler=None) -> None:
        nonlocal completed, failed
        try:
            DeepRepository.add_task_log(task_id, f"正在采集条目 #{item_id}...")
            result = await DeepRepository.collect_single_item(item_id, model, crawler)
            async with lock:
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
                DeepRepository.update_task_progress(task_id, completed, failed)
        except Exception as exc:
            async with lock:
                failed += 1
                DeepRepository.add_task_log(
                    task_id, f"条目 #{item_id} 异常: {str(exc)[:100]}"
                )
                DeepRepository.update_task_progress(task_id, completed, failed)

    # Primary: shared crawl4ai browser for all items, run concurrently.
    # Use BaseException so asyncio.CancelledError (Python 3.11+ BaseException)
    # is caught and we fall through to the per-item fallback instead of
    # aborting the entire batch.
    executor = ConcurrentExecutor("dynamic")
    crawler_ok = False
    try:
        from crawl4ai import AsyncWebCrawler

        async with AsyncWebCrawler(verbose=False) as crawler:
            crawler_ok = True
            coros = [_process_one(item_id, crawler) for item_id in item_ids]
            await executor.run_concurrent(coros)
    except BaseException as crawler_err:
        if crawler_ok:
            # Crawler was alive but died mid-batch; re-raise to avoid silent data loss
            DeepRepository.add_task_log(
                task_id, f"共享爬虫运行中断: {str(crawler_err)[:100]}"
            )
        else:
            DeepRepository.add_task_log(
                task_id, f"共享爬虫初始化失败，降级为独立模式: {str(crawler_err)[:100]}"
            )
        if not crawler_ok:
            coros = [_process_one(item_id) for item_id in item_ids]
            await executor.run_concurrent(coros)

    if failed == 0:
        DeepRepository.complete_task(task_id)
    else:
        DeepRepository.complete_task(task_id)
        DeepRepository.add_task_log(
            task_id, f"采集完成: 成功 {completed} 条, 失败 {failed} 条"
        )
