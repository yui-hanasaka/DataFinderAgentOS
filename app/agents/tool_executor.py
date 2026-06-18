import importlib.metadata
import json
import sys
import urllib.parse
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tornado.ioloop import IOLoop

from app.agents.code_sandbox import execute as sandbox_execute
from app.models.db import get_connection
from app.models.errors import log_error
from app.models.validators import is_safe_public_url


async def _web_search(query: str, max_results: int = 5) -> str:
    """Web search with Bing+DDG fallback chain — works in China."""

    async def _bing_search() -> str:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&setlang=zh-cn"
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        ) as client:
            r = await client.get(url, follow_redirects=True)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(r.content, "html.parser")
        results: list[str] = []
        for li in soup.select("li.b_algo, .b_results li, ol#b_results > li")[
            :max_results
        ]:
            title_el = li.select_one("h2 a, .b_title a")
            snippet_el = li.select_one(".b_caption p, .b_lineclamp2, .b_algoSlug, p")
            title = title_el.get_text(strip=True) if title_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if title:
                results.append(f"{title}\n{snippet}" if snippet else title)
        if results:
            return "\n\n".join(results)
        raise RuntimeError("Bing returned empty results")

    async def _ddg_search() -> str:
        url = (
            f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}"
            f"&format=json&no_redirect=1"
        )
        async with httpx.AsyncClient(timeout=httpx.Timeout(5)) as client:
            r = await client.get(url, follow_redirects=True)
        data = r.json()
        results: list[str] = []
        abstract = data.get("AbstractText", "")
        if abstract:
            results.append(abstract)
        for topic in (data.get("RelatedTopics") or [])[:max_results]:
            text = topic.get("Text", "")
            if text:
                results.append(text)
        if results:
            return "\n\n".join(results[:max_results])
        raise RuntimeError("DDG returned empty results")

    for name, fn in [("bing", _bing_search), ("ddg", _ddg_search)]:
        try:
            result = await fn()
            if result:
                return result
        except Exception as exc:
            log_error(f"tool_executor web_search {name}", exc)
    return "搜索暂时不可用，请稍后重试"


def _fetch_url_sync(url: str) -> str:
    if not is_safe_public_url(url):
        raise ValueError(f"URL 不安全，拒绝访问内网地址: {url}")
    import requests

    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)[:5000]


async def _deep_collect(url: str) -> str:
    if not url or not is_safe_public_url(url):
        return f"采集失败: URL 不安全，拒绝访问内网地址: {url}"
    try:
        text = await IOLoop.current().run_in_executor(None, _fetch_url_sync, url)
    except Exception as exc:
        log_error("tool_executor deep_collect fetch", exc)
        return f"采集失败: {exc}"

    # Try to find existing watchtower item by URL
    item_id: int | None = None
    item_title = url
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, title FROM watchtower_items WHERE url=? ORDER BY id DESC LIMIT 1",
                (url,),
            ).fetchone()
            if row:
                item_id = int(row["id"])
                item_title = row["title"] or url
    except Exception as exc:
        log_error("tool_executor deep_collect find_item", exc)

    # AI analysis with default model
    summary = text[:500]
    keywords = "[]"
    sentiment = ""
    risk = 0
    markdown = ""

    try:
        from app.models.model_engine import ModelRepository
        from app.models.model_client import chat_complete, parse_chat_response

        model = ModelRepository.get_default_model()
        if model and model.get("api_key"):
            prompt = (
                "请分析以下文章内容并以JSON格式返回结果（不要包含markdown代码块标记）：\n"
                f"标题：{item_title}\n"
                f"内容：{text[:3000]}\n\n"
                "请返回以下JSON结构：\n"
                '{"summary": "200字以内的中文摘要",'
                '"keywords": ["关键词1", "关键词2", "关键词3"],'
                '"sentiment": "positive/negative/neutral",'
                '"risk": 0-10的整数风险评分,'
                '"markdown": "整理后的markdown格式内容"}'
            )
            resp = await chat_complete(
                str(model["base_url"]),
                str(model["api_key"]),
                str(model["model_id"]),
                [
                    {
                        "role": "system",
                        "content": "你是一个专业的内容分析助手，请严格以JSON格式返回结果，不要包含```json标记。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1024,
                stream=False,
            )
            raw = await resp.aread()
            parsed = parse_chat_response(raw)
            content_str = str(parsed.get("content", "{}")).strip()
            if content_str.startswith("```"):
                lines = content_str.split("\n")
                content_str = "\n".join(
                    lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                )
            if not content_str:
                content_str = "{}"
            try:
                result = json.loads(content_str)
            except json.JSONDecodeError:
                from app.models.deep import _repair_truncated_json

                content_str = _repair_truncated_json(content_str)
                result = json.loads(content_str)
            summary = str(result.get("summary", text[:200]))
            keywords = json.dumps(list(result.get("keywords", [])), ensure_ascii=False)
            sentiment = str(result.get("sentiment", ""))
            risk = int(result.get("risk", 0))
            markdown = str(result.get("markdown", ""))
    except Exception as exc:
        log_error("tool_executor deep_collect summarize", exc)

    # Save to database if we have an item
    if item_id is not None:
        try:
            with get_connection() as conn:
                conn.execute(
                    """INSERT INTO deep_contents(item_id, task_id, title, url,
                       markdown, plain_text, summary, keywords, sentiment, risk)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item_id,
                        None,
                        item_title,
                        url,
                        markdown,
                        text[:5000],
                        summary,
                        keywords,
                        sentiment,
                        risk,
                    ),
                )
                conn.execute(
                    """UPDATE watchtower_items SET is_deep_collected=1,
                       deep_collected_at=datetime('now') WHERE id=?""",
                    (item_id,),
                )
        except Exception as exc:
            log_error("tool_executor deep_collect save", exc)

    return json.dumps(
        {
            "url": url,
            "title": item_title,
            "summary": summary,
            "keywords": keywords,
            "sentiment": sentiment,
            "risk": risk,
            "content_preview": text[:500],
            "saved_to_db": item_id is not None,
        },
        ensure_ascii=False,
    )


def _watchtower_search(keywords: str, limit: int = 20) -> str:
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT title, url, content, sentiment FROM watchtower_items"
                " WHERE title LIKE ? OR content LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{keywords}%", f"%{keywords}%", limit),
            ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)
    except Exception as exc:
        log_error("tool_executor watchtower_search", exc)
        return f"搜索失败: {exc}"


# Public tables accessible via AI warehouse query — only collected/warehouse data
_WAREHOUSE_SCHEMA_TABLES = {
    "watchtower_items": [
        "id",
        "source_id",
        "title",
        "content",
        "url",
        "sentiment",
        "risk",
        "published_at",
        "collected_at",
        "is_deep_collected",
        "deep_collected_at",
        "deep_task_id",
        "summary",
        "keywords",
        "created_at",
    ],
    "watchtower_sources": [
        "id",
        "name",
        "source_type",
        "url",
        "fetch_interval",
        "status",
        "last_fetched",
        "created_at",
    ],
    "deep_contents": [
        "id",
        "item_id",
        "task_id",
        "title",
        "url",
        "summary",
        "keywords",
        "sentiment",
        "risk",
        "created_at",
    ],
}


def _build_schema_hint() -> str:
    hints = []
    for table, cols in _WAREHOUSE_SCHEMA_TABLES.items():
        hints.append(f"{table}({', '.join(cols)})")
    return "; ".join(hints)


async def _warehouse_query(question: str) -> str:
    # Try NL-to-SQL pipeline via default model
    try:
        from app.models.model_engine import ModelRepository
        from app.models.model_client import chat_complete, parse_chat_response
        from app.models.warehouse import WarehouseRepository

        model = ModelRepository.get_default_model()
        if model and model.get("api_key") and question.strip():
            schema = _build_schema_hint()
            prompt = (
                f"数据库表结构（只读，只能查询以下表）：{schema}\n\n"
                f"请将以下自然语言转换为 SQLite SELECT 语句，只返回 SQL，不要解释：\n{question}"
            )
            resp = await chat_complete(
                str(model["base_url"]),
                str(model["api_key"]),
                str(model["model_id"]),
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=512,
                stream=False,
            )
            raw = await resp.aread()
            parsed = parse_chat_response(raw)
            sql = str(parsed.get("content", "")).strip()
            if sql.startswith("```"):
                sql = sql.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            if sql.strip().upper().startswith("SELECT"):
                rows, _cols, err = WarehouseRepository.execute_query(sql)
                if not err and rows:
                    return json.dumps(
                        [dict(r) for r in rows], ensure_ascii=False, default=str
                    )
    except Exception as exc:
        log_error("tool_executor warehouse_query nl_to_sql", exc)

    # Fallback: simple LIKE search on title, content, summary
    try:
        like = f"%{question}%"
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT wi.title, wi.url, wi.summary, wi.sentiment, dc.summary AS deep_summary"
                " FROM watchtower_items wi"
                " LEFT JOIN deep_contents dc ON dc.item_id = wi.id"
                " WHERE wi.title LIKE ? OR wi.content LIKE ? OR wi.summary LIKE ?"
                " OR dc.summary LIKE ?"
                " ORDER BY wi.id DESC LIMIT 20",
                (like, like, like, like),
            ).fetchall()
        return json.dumps(
            [
                {
                    "title": r["title"],
                    "url": r["url"],
                    "summary": r["deep_summary"] or r["summary"],
                    "sentiment": r["sentiment"],
                }
                for r in rows
            ],
            ensure_ascii=False,
        )
    except Exception as exc:
        log_error("tool_executor warehouse_query fallback", exc)
        return f"查询失败: {exc}"


def _env_info() -> str:
    info = [f"Python {sys.version}", f"平台: {sys.platform}"]
    pkgs = [
        "tornado",
        "httpx",
        "beautifulsoup4",
        "requests",
        "crawl4ai",
        "cryptography",
        "pyright",
        "ruff",
    ]
    for pkg in pkgs:
        try:
            ver = importlib.metadata.version(pkg)
            info.append(f"  {pkg}=={ver}")
        except importlib.metadata.PackageNotFoundError:
            info.append(f"  {pkg} (未安装)")
    return "\n".join(info)


async def execute(name: str, args: dict[str, Any]) -> str:
    match name:
        case "web_search":
            return await _web_search(
                str(args.get("query", "")), int(args.get("max_results", 5))
            )
        case "code_execute":
            return await sandbox_execute(str(args.get("code", "")))
        case "watchtower_search":
            return _watchtower_search(
                str(args.get("keywords", "")), int(args.get("limit", 20))
            )
        case "warehouse_query":
            return await _warehouse_query(str(args.get("question", "")))
        case "deep_collect":
            return await _deep_collect(str(args.get("url", "")))
        case "env_info":
            return _env_info()
        case _:
            return f"未知工具: {name}"
