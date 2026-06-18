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


async def _web_fetch(url: str, save_html: bool = True) -> str:
    """Download a URL's HTML content and save to agent workspace.

    Returns JSON with file_path, content_preview, content_length, status_code.
    The agent can then use code_execute + BeautifulSoup to parse the saved file.
    """
    if not url or not is_safe_public_url(url):
        return json.dumps(
            {"error": "URL 不安全，拒绝访问内网地址", "url": url},
            ensure_ascii=False,
        )

    import time as _time
    from urllib.parse import urlparse as _urlparse

    from app.agents.code_sandbox import _ensure_workspace, _WORKSPACE_ROOT

    _ensure_workspace()
    downloads_dir = _WORKSPACE_ROOT / "downloads"

    parsed = _urlparse(url)
    host = (parsed.hostname or "unknown").replace(".", "_")
    ts = str(int(_time.time() * 1_000_000))
    filename = f"{host}_{ts}.html"
    filepath = downloads_dir / filename

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            follow_redirects=True,
        ) as client:
            r = await client.get(url)
        content = r.text
        content_type = r.headers.get("content-type", "")

        preview = content[:3000]
        if save_html:
            filepath.write_text(content, encoding="utf-8")
            saved_path = str(filepath)
        else:
            saved_path = ""

        return json.dumps(
            {
                "url": url,
                "status_code": r.status_code,
                "content_type": content_type,
                "content_length": len(content),
                "file_path": saved_path,
                "content_preview": preview,
                "hint": (
                    "HTML已保存到工作区。"
                    "请用 code_execute 工具编写 BeautifulSoup 脚本解析此文件，"
                    f"文件路径: {saved_path}"
                    if saved_path
                    else "HTML未保存。请用 code_execute 工具直接分析 content_preview。"
                ),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        log_error(f"tool_executor web_fetch url={url[:60]}", exc)
        return json.dumps(
            {"error": f"下载失败: {exc}", "url": url},
            ensure_ascii=False,
        )


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
                # Bing anti-bot garbage detector: if query is CJK but all
                # results are CJK-free, treat as empty and fall through.
                if name == "bing" and _bing_garbage(result, query):
                    log_error(
                        f"tool_executor web_search {name} garbage — falling through",
                        RuntimeError("garbage"),
                    )
                    continue
                return result
        except Exception as exc:
            log_error(f"tool_executor web_search {name}", exc)
    return "搜索暂时不可用，请稍后重试"


def _bing_garbage(results: str, query: str) -> bool:
    """True when Bing returned anti-bot filler (zero CJK in any block
    for a query that contains CJK characters)."""
    import re

    if not re.search(r"[一-鿿]", query):
        return False
    blocks = [b for b in results.split("\n\n") if b.strip()]
    if not blocks:
        return False
    return all(not re.search(r"[一-鿿]", b) for b in blocks)


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
                "SELECT title, url, content, sentiment, summary FROM watchtower_items"
                " WHERE title LIKE ? OR content LIKE ? OR summary LIKE ?"
                " ORDER BY id DESC LIMIT ?",
                (f"%{keywords}%", f"%{keywords}%", f"%{keywords}%", limit),
            ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)
    except Exception as exc:
        log_error("tool_executor watchtower_search", exc)
        return f"搜索失败: {exc}"


def _watchtower_insert(
    title: str,
    content: str,
    url: str = "",
    source_name: str = "AI采集",
    sentiment: str = "",
    risk: int = 0,
) -> str:
    """Insert an item into watchtower_items, auto-creating source if needed."""
    if not title.strip() or not content.strip():
        return json.dumps({"error": "标题和内容不能为空"}, ensure_ascii=False)
    try:
        with get_connection() as conn:
            # Find or create source
            source_id: int | None = None
            if source_name.strip():
                row = conn.execute(
                    "SELECT id FROM watchtower_sources WHERE name=? LIMIT 1",
                    (source_name.strip(),),
                ).fetchone()
                if row:
                    source_id = int(row["id"])
                else:
                    cur = conn.execute(
                        "INSERT INTO watchtower_sources(name, source_type, url, status)"
                        " VALUES(?,?,?,?)",
                        (source_name.strip(), "generic", "", "enabled"),
                    )
                    source_id = int(cur.lastrowid)

            # Insert item (skip duplicate URLs)
            try:
                cur = conn.execute(
                    "INSERT INTO watchtower_items(source_id, title, content, url,"
                    " sentiment, risk, collected_at)"
                    " VALUES(?,?,?,?,?,?,datetime('now'))",
                    (
                        source_id,
                        title.strip(),
                        content.strip(),
                        url.strip(),
                        sentiment.strip() or "neutral",
                        risk,
                    ),
                )
                item_id = int(cur.lastrowid)
                return json.dumps(
                    {
                        "ok": True,
                        "item_id": item_id,
                        "source_name": source_name,
                        "title": title.strip(),
                        "action": "created",
                    },
                    ensure_ascii=False,
                )
            except Exception:
                # Likely duplicate URL — try to find existing
                if url.strip():
                    row = conn.execute(
                        "SELECT id, title FROM watchtower_items WHERE url=? LIMIT 1",
                        (url.strip(),),
                    ).fetchone()
                    if row:
                        return json.dumps(
                            {
                                "ok": True,
                                "item_id": int(row["id"]),
                                "title": row["title"],
                                "action": "skipped_duplicate",
                            },
                            ensure_ascii=False,
                        )
                raise
    except Exception as exc:
        log_error("tool_executor watchtower_insert", exc)
        return json.dumps({"error": f"插入失败: {exc}"}, ensure_ascii=False)


def _watchtower_iterative_search(
    keywords: str,
    iteration: int = 1,
    max_iterations: int = 3,
    refinement: str = "",
    limit: int = 20,
) -> str:
    """Multi-turn iterative search with refinement tracking."""
    results = _watchtower_search(keywords, limit)
    try:
        result_data = json.loads(results)
    except json.JSONDecodeError:
        result_data = []
    count = len(result_data) if isinstance(result_data, list) else 0

    # Log iteration to DB if session tracking is available
    try:
        with get_connection() as conn:
            # Try to find or create session (best-effort)
            if iteration == 1:
                cur = conn.execute(
                    "INSERT INTO watchtower_ai_search_sessions(query) VALUES(?)",
                    (keywords,),
                )
                session_id = int(cur.lastrowid)
            else:
                row = conn.execute(
                    "SELECT id FROM watchtower_ai_search_sessions"
                    " ORDER BY id DESC LIMIT 1"
                ).fetchone()
                session_id = int(row["id"]) if row else None

            if session_id:
                conn.execute(
                    "INSERT INTO watchtower_ai_search_iterations"
                    "(session_id, iteration, keywords, results_count, refinement)"
                    " VALUES(?,?,?,?,?)",
                    (session_id, iteration, keywords, count, refinement),
                )
                conn.execute(
                    "UPDATE watchtower_ai_search_sessions"
                    " SET iterations=iterations+1, total_results=total_results+?"
                    " WHERE id=?",
                    (count, session_id),
                )
                if iteration >= max_iterations:
                    conn.execute(
                        "UPDATE watchtower_ai_search_sessions"
                        " SET status='completed', finished_at=datetime('now')"
                        " WHERE id=?",
                        (session_id,),
                    )
    except Exception as exc:
        log_error("tool_executor watchtower_iterative_search log", exc)

    return json.dumps(
        {
            "iteration": iteration,
            "max_iterations": max_iterations,
            "keywords": keywords,
            "results_count": count,
            "results": result_data,
            "hint": (
                f"第{iteration}轮搜索完成，找到{count}条结果。"
                f"如需优化关键词继续搜索，请增加 iteration 参数。"
                if count > 0
                else f"第{iteration}轮未找到结果。建议更换关键词重试。"
            ),
        },
        ensure_ascii=False,
    )


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


async def _weather_query(
    city: str = "",
    adcode: str = "",
    forecast: bool = True,
    hourly: bool = True,
    minutely: bool = True,
    indices: bool = True,
    lang: str = "zh",
) -> str:
    """Query weather via uapis.cn free API — no key required.

    Supports: city name, adcode, or auto-IP-location (when both empty).
    Returns all modules by default (extended, forecast, hourly, minutely, indices).
    """
    try:
        import urllib.parse

        params = []
        if adcode.strip():
            params.append(f"adcode={urllib.parse.quote(adcode.strip())}")
        elif city.strip():
            params.append(f"city={urllib.parse.quote(city.strip())}")
        # else: neither → auto IP location

        params.append("extended=true")
        if forecast:
            params.append("forecast=true")
        if hourly:
            params.append("hourly=true")
        if minutely:
            params.append("minutely=true")
        if indices:
            params.append("indices=true")
        if lang and lang != "zh":
            params.append(f"lang={urllib.parse.quote(lang)}")

        url = f"https://uapis.cn/api/v1/misc/weather?{'&'.join(params)}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
            r = await client.get(url)
        if r.status_code == 404:
            loc = adcode or city or "当前IP位置"
            return json.dumps(
                {"error": f"未找到「{loc}」的天气数据，请检查城市名称或行政区划代码"},
                ensure_ascii=False,
            )
        if r.status_code != 200:
            return json.dumps(
                {"error": f"天气服务返回 {r.status_code}，请稍后重试"},
                ensure_ascii=False,
            )
        data = r.json()

        # Build a concise but complete response
        result: dict[str, Any] = {
            "location": {
                "province": data.get("province", ""),
                "city": data.get("city", ""),
                "district": data.get("district", ""),
                "adcode": data.get("adcode", ""),
            },
            "current": {
                "weather": data.get("weather", ""),
                "weather_icon": data.get("weather_icon", ""),
                "temperature": data.get("temperature"),
                "feels_like": data.get("feels_like"),
                "humidity": data.get("humidity"),
                "wind_direction": data.get("wind_direction", ""),
                "wind_power": data.get("wind_power", ""),
                "visibility": data.get("visibility"),
                "pressure": data.get("pressure"),
                "uv": data.get("uv"),
                "precipitation": data.get("precipitation"),
                "cloud": data.get("cloud"),
                "report_time": data.get("report_time", ""),
            },
        }

        # Air quality
        if data.get("aqi") is not None:
            result["air_quality"] = {
                "aqi": data.get("aqi"),
                "level": data.get("aqi_level"),
                "category": data.get("aqi_category", ""),
                "primary_pollutant": data.get("aqi_primary", ""),
                "pollutants": data.get("air_pollutants"),
            }

        # Weather alerts
        alerts = data.get("alerts")
        if alerts:
            result["alerts"] = alerts

        # Daily temperature range
        if data.get("temp_max") is not None:
            result["today_range"] = {
                "temp_max": data.get("temp_max"),
                "temp_min": data.get("temp_min"),
            }

        # 7-day forecast
        if forecast and data.get("forecast"):
            result["forecast"] = data["forecast"]

        # 24-hour hourly forecast
        if hourly and data.get("hourly_forecast"):
            result["hourly_forecast"] = data["hourly_forecast"]

        # Minute-level precipitation
        if minutely and data.get("minutely_precip"):
            result["minutely_precip"] = data["minutely_precip"]

        # 18 life indices
        if indices and data.get("life_indices"):
            result["life_indices"] = data["life_indices"]

        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        loc = adcode or city or "auto"
        log_error(f"tool_executor weather_query loc={loc}", exc)
        return json.dumps({"error": f"天气查询失败: {exc}"}, ensure_ascii=False)


async def _music_search(query: str) -> str:
    """Search songs via chinokou.cn Netease API."""
    if not query.strip():
        return json.dumps({"error": "请提供搜索关键词"}, ensure_ascii=False)
    try:
        import urllib.parse

        encoded = urllib.parse.quote(query.strip())
        url = f"https://music.chinokou.cn/cloudsearch?keywords={encoded}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return json.dumps(
                {"error": f"音乐搜索返回 {r.status_code}，请稍后重试"},
                ensure_ascii=False,
            )
        data = r.json()
        songs = []
        raw_songs = (data.get("result") or {}).get("songs") or []
        for s in raw_songs[:10]:
            ar = (s.get("ar") or [{}])[0].get("name", "")
            songs.append(
                {
                    "id": s.get("id"),
                    "title": s.get("name", ""),
                    "artist": ar,
                    "album": (s.get("al") or {}).get("name", ""),
                }
            )
        return json.dumps(
            {"query": query, "count": len(songs), "songs": songs},
            ensure_ascii=False,
        )
    except Exception as exc:
        log_error(f"tool_executor music_search query={query}", exc)
        return json.dumps({"error": f"音乐搜索失败: {exc}"}, ensure_ascii=False)


async def _music_detail(song_id: int) -> str:
    """Get song detail including cover art URL via chinokou.cn."""
    try:
        url = f"https://music.chinokou.cn/song/detail?ids={song_id}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return json.dumps(
                {"error": f"歌曲详情查询返回 {r.status_code}"},
                ensure_ascii=False,
            )
        data = r.json()
        songs = data.get("songs") or []
        if not songs:
            return json.dumps(
                {"error": f"未找到歌曲 ID={song_id} 的详情"},
                ensure_ascii=False,
            )
        s = songs[0]
        al = s.get("al") or {}
        ar_list = s.get("ar") or [{}]
        cover_url = al.get("picUrl") or ""
        # Apply image resize param for consistent size
        if cover_url and "?" not in cover_url:
            cover_url = f"{cover_url}?param=300y300"
        return json.dumps(
            {
                "song_id": s.get("id"),
                "title": s.get("name", ""),
                "artist": ", ".join(a.get("name", "") for a in ar_list),
                "album": al.get("name", ""),
                "cover_url": cover_url,
                "duration_ms": int(s.get("dt") or 0),
                "duration_sec": int(s.get("dt") or 0) // 1000,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        log_error(f"tool_executor music_detail song_id={song_id}", exc)
        return json.dumps({"error": f"歌曲详情查询失败: {exc}"}, ensure_ascii=False)


async def _music_play(song_id: int, title: str = "", artist: str = "") -> str:
    """Download audio via chinokou.cn song/url, base64-encode, return to frontend."""
    if not song_id:
        return json.dumps({"error": "请提供歌曲ID"}, ensure_ascii=False)
    try:
        import base64

        # 1. Get audio URL from song/url
        url_api = f"https://music.chinokou.cn/song/url?id={song_id}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
            r = await client.get(url_api)
        if r.status_code != 200:
            return json.dumps(
                {"error": f"获取音频地址返回 {r.status_code}"},
                ensure_ascii=False,
            )
        url_data = r.json()
        url_entries = url_data.get("data") or []
        if not url_entries:
            return json.dumps(
                {"error": "未获取到音频下载地址，可能无版权"},
                ensure_ascii=False,
            )
        audio_url = url_entries[0].get("url", "")
        if not audio_url:
            return json.dumps(
                {"error": "音频链接为空，可能无版权或需登录"},
                ensure_ascii=False,
            )
        br = url_entries[0].get("br", 0)
        content_type = url_entries[0].get("type", "mp3")

        # 2. Download audio
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Referer": "https://music.163.com/",
            },
            follow_redirects=True,
        ) as client:
            audio_resp = await client.get(audio_url)
        if audio_resp.status_code != 200:
            return json.dumps(
                {"error": f"下载音频失败 HTTP {audio_resp.status_code}"},
                ensure_ascii=False,
            )
        audio_bytes = audio_resp.content
        audio_size = len(audio_bytes)

        # 3. Get cover art from song/detail
        cover_url = ""
        try:
            detail_url = f"https://music.chinokou.cn/song/detail?ids={song_id}"
            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
                detail_r = await client.get(detail_url)
            if detail_r.status_code == 200:
                detail_data = detail_r.json()
                songs = detail_data.get("songs") or []
                if songs:
                    s = songs[0]
                    title = s.get("name") or title
                    al = s.get("al") or {}
                    cover_url = al.get("picUrl") or ""
                    if cover_url and "?" not in cover_url:
                        cover_url = f"{cover_url}?param=300y300"
                    ar_list = s.get("ar") or [{}]
                    artist = artist or ", ".join(a.get("name", "") for a in ar_list)
        except Exception:
            pass  # detail fetch is best-effort; play still works without it

        # 4. Base64 encode
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

        # 5. Save to workspace for persistence
        from app.agents.code_sandbox import _ensure_workspace, _WORKSPACE_ROOT

        _ensure_workspace()
        ext = content_type if content_type else "mp3"
        out_path = _WORKSPACE_ROOT / "output" / f"song_{song_id}.{ext}"
        out_path.write_bytes(audio_bytes)

        return json.dumps(
            {
                "song_id": song_id,
                "title": title,
                "artist": artist,
                "cover_url": cover_url,
                "audio_base64": audio_b64,
                "format": content_type,
                "bitrate": br,
                "size_bytes": audio_size,
                "hint": (
                    f"音频已下载并base64编码（{audio_size // 1024}KB）。"
                    "前端可通过解码base64创建Blob URL播放。"
                ),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        log_error(f"tool_executor music_play song_id={song_id}", exc)
        return json.dumps({"error": f"播放失败: {exc}"}, ensure_ascii=False)


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
        case "web_fetch":
            return await _web_fetch(
                str(args.get("url", "")),
                bool(args.get("save_html", True)),
            )
        case "watchtower_search":
            return _watchtower_search(
                str(args.get("keywords", "")), int(args.get("limit", 20))
            )
        case "watchtower_insert":
            return _watchtower_insert(
                str(args.get("title", "")),
                str(args.get("content", "")),
                str(args.get("url", "")),
                str(args.get("source_name", "AI采集")),
                str(args.get("sentiment", "")),
                int(args.get("risk", 0)),
            )
        case "watchtower_iterative_search":
            return _watchtower_iterative_search(
                str(args.get("keywords", "")),
                int(args.get("iteration", 1)),
                int(args.get("max_iterations", 3)),
                str(args.get("refinement", "")),
                int(args.get("limit", 20)),
            )
        case "warehouse_query":
            return await _warehouse_query(str(args.get("question", "")))
        case "deep_collect":
            return await _deep_collect(str(args.get("url", "")))
        case "env_info":
            return _env_info()
        case "weather_query":
            return await _weather_query(
                str(args.get("city", "")),
                str(args.get("adcode", "")),
                bool(args.get("forecast", True)),
                bool(args.get("hourly", True)),
                bool(args.get("minutely", True)),
                bool(args.get("indices", True)),
                str(args.get("lang", "zh")),
            )
        case "music_search":
            return await _music_search(str(args.get("query", "")))
        case "music_detail":
            return await _music_detail(int(args.get("song_id", 0)))
        case "music_play":
            return await _music_play(
                int(args.get("song_id", 0)),
                str(args.get("title", "")),
                str(args.get("artist", "")),
            )
        case _:
            return f"未知工具: {name}"
