import json
from datetime import datetime

from app.models.db import get_connection
from app.models.errors import log_error
from app.models.model_client import chat_complete, parse_chat_response
from app.models.model_engine import ModelRepository


PER_PAGE = 20


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
                   target_item_ids, total_items, progress)
                   VALUES(?, ?, 1, 'running', ?, ?, 0)""",
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
    async def collect_single_item(item_id: int, model: dict | None) -> dict:
        """Deep collect a single item: scrape content, summarize with model.
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

        # Step 1: Try to scrape the URL for content
        content_text = item["content"] or ""
        try:
            from tornado.ioloop import IOLoop

            import requests
            from bs4 import BeautifulSoup

            if item["url"] and item["url"].startswith("http"):

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
                f"DeepRepository.collect_single_item fetch_url item_id={item_id} url={item['url']}",
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
        """Use the model to summarize and analyze content."""
        prompt = f"""请分析以下文章内容并以JSON格式返回结果（不要包含markdown代码块标记）：
标题：{title}
内容：{content[:3000]}

请返回以下JSON结构：
{{
    "summary": "200字以内的中文摘要",
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "sentiment": "positive/negative/neutral",
    "risk": 0-10的整数风险评分,
    "markdown": "整理后的markdown格式内容"
}}"""

        messages = [
            {
                "role": "system",
                "content": "你是一个专业的内容分析助手，请严格以JSON格式返回结果，不要包含```json标记。",
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
                max_tokens=1024,
                stream=False,
            )
            raw = await resp.aread()
            parsed = parse_chat_response(raw)
            content_str: str = str(parsed.get("content", "{}"))
            content_str = content_str.strip()
            if content_str.startswith("```"):
                lines = content_str.split("\n")
                content_str = "\n".join(
                    lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                )
            return json.loads(content_str)
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
                "markdown": content,
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
        """Update task progress counters."""
        with get_connection() as conn:
            conn.execute(
                """UPDATE deep_tasks SET completed_items=?, failed_items=?,
                   progress=CASE WHEN total_items>0 THEN
                   CAST((completed_items * 1.0 / total_items) * 100 AS INTEGER)
                   ELSE 0 END
                   WHERE id=?""",
                (completed, failed, task_id),
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
        """Add a log entry to a task."""
        logs = DeepRepository.get_task_logs(task_id)
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        with get_connection() as conn:
            conn.execute(
                "UPDATE deep_tasks SET logs=? WHERE id=?",
                (json.dumps(logs, ensure_ascii=False), task_id),
            )
