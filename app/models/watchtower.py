import json
import sqlite3

from app.models.db import get_connection
from app.models.errors import log_error


async def analyze_items_sentiment(item_ids: list[int]) -> int:
    """对指定条目调用默认模型进行情感+风险分析，并更新 sentiment/risk 字段。

    返回成功分析的条目数量。
    """
    from app.models.model_client import chat_complete, parse_chat_response
    from app.models.model_engine import ModelRepository
    from app.models.secrets_store import decrypt

    model = ModelRepository.get_default_model()
    if not model:
        return 0

    api_key = decrypt(str(model["api_key"]))
    if not api_key:
        return 0

    analyzed = 0
    for item_id in item_ids[:20]:  # 单次最多分析 20 条
        try:
            item = ItemRepository.get_item(item_id)
            if not item:
                continue

            title = item["title"] or ""
            content = (item["content"] or "")[:1000]

            prompt = (
                "请分析以下信息条目，以JSON格式返回结果（不要包含markdown代码块标记）：\n"
                f"标题：{title}\n"
                f"内容：{content}\n\n"
                '返回JSON：{"sentiment":"positive/negative/neutral","risk":0-10,"summary":"50字以内中文摘要"}'
            )

            resp = await chat_complete(
                str(model["base_url"]),
                api_key,
                str(model["model_id"]),
                [
                    {
                        "role": "system",
                        "content": "你是信息分析助手，严格以JSON格式返回结果，不要包含```json标记。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=256,
                stream=False,
            )
            parsed = parse_chat_response(resp.content)
            raw_content = str(parsed.get("content", "{}")).strip()
            raw_content = (
                raw_content.removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            result = json.loads(raw_content)
            sentiment = str(result.get("sentiment", "neutral"))
            risk = str(result.get("risk", 0))
            ItemRepository.update_sentiment(item_id, sentiment, risk)
            analyzed += 1
        except Exception as e:
            log_error(f"analyze_items_sentiment item_id={item_id}", e)

    return analyzed


class SourceRepository:
    @staticmethod
    def list_sources(keyword: str = "", page: int = 1) -> tuple[list[sqlite3.Row], int]:
        per_page = 20
        offset = (page - 1) * per_page
        like = f"%{keyword}%"
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM watchtower_sources WHERE name LIKE ?", (like,)
            ).fetchone()[0]
            rows = conn.execute(
                """SELECT s.*, (SELECT COUNT(*) FROM watchtower_items WHERE source_id=s.id) AS item_count
                   FROM watchtower_sources s WHERE s.name LIKE ? ORDER BY s.id DESC LIMIT ? OFFSET ?""",
                (like, per_page, offset),
            ).fetchall()
        return rows, total

    @staticmethod
    def get_source(source_id: int) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM watchtower_sources WHERE id=?", (source_id,)
            ).fetchone()

    @staticmethod
    def create_source(
        name: str,
        source_type: str,
        url: str,
        fetch_interval: int,
        status: str,
        url_template: str = "",
        request_headers: str = "",
        config_json: str = "{}",
    ) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO watchtower_sources(name, source_type, url, fetch_interval,
                       status, url_template, request_headers, config_json)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        name,
                        source_type,
                        url,
                        fetch_interval,
                        status,
                        url_template,
                        request_headers,
                        config_json,
                    ),
                )
            return True, None
        except Exception as e:
            log_error("Watchtower.create_source", e)
            return False, "创建采集源失败"

    @staticmethod
    def update_source(
        source_id: int,
        name: str,
        source_type: str,
        url: str,
        fetch_interval: int,
        status: str,
        url_template: str = "",
        request_headers: str = "",
        config_json: str = "{}",
    ) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    """UPDATE watchtower_sources SET name=?, source_type=?, url=?,
                       fetch_interval=?, status=?, url_template=?, request_headers=?,
                       config_json=?, updated_at=datetime('now') WHERE id=?""",
                    (
                        name,
                        source_type,
                        url,
                        fetch_interval,
                        status,
                        url_template,
                        request_headers,
                        config_json,
                        source_id,
                    ),
                )
            return True, None
        except Exception as e:
            log_error("Watchtower.update_source", e)
            return False, "更新采集源失败"

    @staticmethod
    def delete_source(source_id: int) -> tuple[bool, str | None]:
        try:
            with get_connection() as conn:
                conn.execute(
                    "DELETE FROM watchtower_items WHERE source_id=?", (source_id,)
                )
                conn.execute("DELETE FROM watchtower_sources WHERE id=?", (source_id,))
            return True, None
        except Exception as e:
            log_error("Watchtower.delete_source", e)
            return False, "删除采集源失败"

    @staticmethod
    def mark_fetched(source_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE watchtower_sources SET last_fetched=datetime('now') WHERE id=?",
                (source_id,),
            )

    @staticmethod
    def list_all_enabled() -> list[sqlite3.Row]:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM watchtower_sources WHERE status='enabled' ORDER BY id ASC"
            ).fetchall()


class ItemRepository:
    @staticmethod
    def add_item(data: dict[str, object]) -> int | None:
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO watchtower_items(source_id, title, content, url, published_at)
                   VALUES(?,?,?,?,?)""",
                (
                    data["source_id"],
                    data["title"],
                    data["content"],
                    data["url"],
                    data["published_at"],
                ),
            )
            return cur.lastrowid

    @staticmethod
    def list_items(keyword: str = "", page: int = 1) -> tuple[list[sqlite3.Row], int]:
        per_page = 20
        offset = (page - 1) * per_page
        like = f"%{keyword}%"
        with get_connection() as conn:
            if keyword:
                total = conn.execute(
                    "SELECT COUNT(*) FROM watchtower_items WHERE title LIKE ? OR content LIKE ?",
                    (like, like),
                ).fetchone()[0]
                rows = conn.execute(
                    """SELECT i.*, s.name AS source_name FROM watchtower_items i
                       LEFT JOIN watchtower_sources s ON i.source_id=s.id
                       WHERE i.title LIKE ? OR i.content LIKE ?
                       ORDER BY i.id DESC LIMIT ? OFFSET ?""",
                    (like, like, per_page, offset),
                ).fetchall()
            else:
                total = conn.execute(
                    "SELECT COUNT(*) FROM watchtower_items"
                ).fetchone()[0]
                rows = conn.execute(
                    """SELECT i.*, s.name AS source_name FROM watchtower_items i
                       LEFT JOIN watchtower_sources s ON i.source_id=s.id
                       ORDER BY i.id DESC LIMIT ? OFFSET ?""",
                    (per_page, offset),
                ).fetchall()
        return rows, total

    @staticmethod
    def update_sentiment(item_id: int, sentiment: str, risk: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE watchtower_items SET sentiment=?, risk=? WHERE id=?",
                (sentiment, risk, item_id),
            )

    @staticmethod
    def count_items(keyword: str = "") -> int:
        with get_connection() as conn:
            if keyword:
                like = f"%{keyword}%"
                return conn.execute(
                    "SELECT COUNT(*) FROM watchtower_items WHERE title LIKE ? OR content LIKE ?",
                    (like, like),
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM watchtower_items").fetchone()[0]

    @staticmethod
    def recent_items(limit: int = 12) -> list[sqlite3.Row]:
        with get_connection() as conn:
            return conn.execute(
                """SELECT i.*, s.name AS source_name FROM watchtower_items i
                   LEFT JOIN watchtower_sources s ON i.source_id=s.id
                   ORDER BY i.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()

    @staticmethod
    def get_item(item_id: int) -> sqlite3.Row | None:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM watchtower_items WHERE id=?", (item_id,)
            ).fetchone()

    @staticmethod
    def delete_item(item_id: int) -> tuple[bool, str | None]:
        """删除采集条目及其关联的深度采集内容。"""
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM deep_contents WHERE item_id=?", (item_id,))
                conn.execute("DELETE FROM watchtower_items WHERE id=?", (item_id,))
            return True, None
        except Exception as e:
            log_error("Watchtower.delete_item", e)
            return False, "删除采集数据失败"

    @staticmethod
    def batch_delete_items(item_ids: list[int]) -> tuple[bool, str | None]:
        """批量删除采集条目及其关联的深度采集内容。"""
        try:
            with get_connection() as conn:
                for item_id in item_ids:
                    conn.execute(
                        "DELETE FROM deep_contents WHERE item_id=?", (item_id,)
                    )
                    conn.execute("DELETE FROM watchtower_items WHERE id=?", (item_id,))
            return True, None
        except Exception as e:
            log_error("Watchtower.batch_delete_items", e)
            return False, "批量删除失败"

    @staticmethod
    def list_items_filtered(
        keyword: str = "",
        source_id: int = 0,
        sentiment: str = "",
        risk_min: int = 0,
        risk_max: int = 10,
        is_deep_collected: int | None = None,
        date_from: str = "",
        date_to: str = "",
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[sqlite3.Row], int]:
        """Filtered + paginated item listing for the data management page."""
        conditions: list[str] = []
        params: list[object] = []

        if keyword:
            like = f"%{keyword}%"
            conditions.append(
                "(i.title LIKE ? OR i.content LIKE ? OR i.summary LIKE ?)"
            )
            params.extend([like, like, like])
        if source_id > 0:
            conditions.append("i.source_id = ?")
            params.append(source_id)
        if sentiment:
            conditions.append("i.sentiment = ?")
            params.append(sentiment)
        if risk_min > 0:
            conditions.append("i.risk >= ?")
            params.append(risk_min)
        if risk_max < 10:
            conditions.append("i.risk <= ?")
            params.append(risk_max)
        if is_deep_collected is not None:
            conditions.append("i.is_deep_collected = ?")
            params.append(is_deep_collected)
        if date_from:
            conditions.append("i.collected_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("i.collected_at <= ?")
            params.append(date_to + " 23:59:59")

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * per_page

        with get_connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM watchtower_items i{where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT i.*, s.name AS source_name FROM watchtower_items i"
                f" LEFT JOIN watchtower_sources s ON i.source_id=s.id"
                f"{where}"
                f" ORDER BY i.id DESC LIMIT ? OFFSET ?",
                params + [per_page, offset],
            ).fetchall()
        return rows, total

    @staticmethod
    def list_all_sources() -> list[sqlite3.Row]:
        """List enabled sources for filter dropdown."""
        with get_connection() as conn:
            return conn.execute(
                "SELECT id, name FROM watchtower_sources"
                " WHERE status='enabled' ORDER BY name"
            ).fetchall()

    @staticmethod
    def export_items(
        item_ids: list[int],
    ) -> tuple[list[sqlite3.Row] | None, str | None]:
        """Export selected items as rows for JSON/CSV download."""
        try:
            with get_connection() as conn:
                placeholders = ",".join("?" for _ in item_ids)
                rows = conn.execute(
                    f"SELECT i.*, s.name AS source_name FROM watchtower_items i"
                    f" LEFT JOIN watchtower_sources s ON i.source_id=s.id"
                    f" WHERE i.id IN ({placeholders}) ORDER BY i.id DESC",
                    item_ids,
                ).fetchall()
            return rows, None
        except Exception as e:
            log_error("Watchtower.export_items", e)
            return None, str(e)

    @staticmethod
    def batch_add_items(items: list[dict]) -> tuple[int, list[int]]:
        """批量保存采集条目，返回 (成功插入数量, 新插入的ID列表)。

        去重策略：相同 source_id + url（非空）在本批次内视为重复，跳过。
        """
        count = 0
        new_ids: list[int] = []
        seen: set[tuple[int, str]] = set()
        with get_connection() as conn:
            for item in items:
                try:
                    src_id = int(item.get("source_id", 0))
                    url = str(item.get("url") or "")
                    # Dedup within batch by (source_id, url); empty URL skips dedup
                    if url:
                        key = (src_id, url)
                        if key in seen:
                            continue
                        seen.add(key)

                    cur = conn.execute(
                        """INSERT OR IGNORE INTO watchtower_items
                           (source_id, title, content, url, published_at, keywords, raw_json)
                           VALUES(?,?,?,?,?,?,?)""",
                        (
                            src_id,
                            item.get("title", ""),
                            item.get("content", ""),
                            url,
                            item.get("published_at", ""),
                            item.get("keywords", "[]"),
                            item.get("raw_json", "{}"),
                        ),
                    )
                    row_id = cur.lastrowid
                    if row_id:
                        count += 1
                        new_ids.append(row_id)
                except Exception as e:
                    log_error("Watchtower.batch_add_items", e)
        return count, new_ids
