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


async def _web_search(query: str, max_results: int = 5) -> str:
    encoded = urllib.parse.quote(query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_redirect=1"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
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
        return "\n\n".join(results[:max_results]) or "未找到相关结果"
    except Exception as exc:
        log_error("tool_executor web_search", exc)
        return f"搜索失败: {exc}"


def _fetch_url_sync(url: str) -> str:
    import requests

    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)[:5000]


async def _deep_collect(url: str) -> str:
    try:
        text = await IOLoop.current().run_in_executor(None, _fetch_url_sync, url)
        return f"已采集URL内容（前5000字符）：\n{text}"
    except Exception as exc:
        log_error("tool_executor deep_collect", exc)
        return f"采集失败: {exc}"


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


def _warehouse_query() -> str:
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT wi.title, wi.url, dc.summary, dc.sentiment"
                " FROM watchtower_items wi"
                " LEFT JOIN deep_contents dc ON dc.item_id = wi.id"
                " WHERE dc.summary IS NOT NULL ORDER BY wi.id DESC LIMIT 20"
            ).fetchall()
        return json.dumps(
            [
                {
                    "title": r["title"],
                    "summary": r["summary"],
                    "sentiment": r["sentiment"],
                }
                for r in rows
            ],
            ensure_ascii=False,
        )
    except Exception as exc:
        log_error("tool_executor warehouse_query", exc)
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
            return _warehouse_query()
        case "deep_collect":
            return await _deep_collect(str(args.get("url", "")))
        case "env_info":
            return _env_info()
        case _:
            return f"未知工具: {name}"
