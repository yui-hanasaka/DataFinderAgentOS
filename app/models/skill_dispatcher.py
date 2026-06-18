import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.models.errors import log_error


def _time_context() -> str:
    """Return a time-awareness prompt for search/agent tool use.

    Injected only when search or agent tool calls are involved — does NOT
    pollute normal conversations.
    """
    _now = datetime.now(timezone(timedelta(hours=8)))
    return (
        f"【当前时间】服务器本地时间是 {_now.strftime('%Y-%m-%d %H:%M:%S')}"
        f"（{_now.strftime('UTC%z')}，北京时间）。"
        "处理“今天、最新、近期、今年”等相对时间、"
        "生成搜索词和筛选搜索结果时，必须以此时间为准；"
        "请核对搜索结果的发布日期，不要把模型训练数据中的日期当作当前日期。"
    )


DispatchResult = dict[str, Any]


async def dispatch(text: str, api_keys: dict[str, str] | None = None) -> DispatchResult:
    keys = api_keys or {}

    m = re.match(r"^@(?:weather|天气)\s+(.+)", text.strip(), re.IGNORECASE)
    if m:
        city = m.group(1).strip()
        return {
            "type": "ai",
            "skill_code": "weather",
            "processed_content": f"查询{city}天气",
            "skill_meta": {
                "inject_prompt": (
                    f"{_time_context()}\n\n"
                    f"请使用 weather_query 工具查询「{city}」的实时天气，"
                    f"然后以友好的语气展示结果。"
                ),
            },
        }

    m2 = re.match(r"^@(?:music|音乐)\s+(.+)", text.strip(), re.IGNORECASE)
    if m2:
        query = m2.group(1).strip()
        return {
            "type": "ai",
            "skill_code": "music",
            "processed_content": f"搜索歌曲：{query}",
            "skill_meta": {
                "inject_prompt": (
                    f"请使用 music_search 工具搜索「{query}」的歌曲。"
                    f"返回结果后，列出歌曲让用户选择（每条显示序号、歌名、歌手）。"
                    f"等用户告诉你想听哪首后，使用 music_play 工具播放。"
                ),
            },
        }

    if re.match(r"^@(?:music|音乐)\b", text.strip(), re.IGNORECASE):
        return {
            "type": "skill",
            "skill_code": "music",
            "processed_content": _music_html(),
            "skill_meta": {"skill_code": "music"},
        }

    m = re.match(r"^@西师妹\s*(.*)", text.strip())
    if m:
        question = m.group(1).strip()
        return {
            "type": "ai",
            "skill_code": "campus",
            "processed_content": question,
            "skill_meta": {
                "system_override": (
                    "你是西南师范大学的校园助手「西师妹」，请用友好活泼的语气回答校园相关问题。"
                    "重要：当用户询问实时信息、新闻、天气、动态等内容时，必须先使用工具搜索，"
                    "展示'正在查找相关信息…'，然后调用 web_search / code_execute 获取信息，"
                    "最后基于搜索结果回答。不要在没有搜索的情况下直接说找不到。"
                ),
            },
        }

    m = re.match(r"^\\(?:search|搜索)\w*\s+(.*)", text.strip(), re.IGNORECASE)
    if m:
        query = m.group(1).strip()
        snippets = await _web_search(query, keys.get("websearch"))
        if "不可用" in snippets or "未找到" in snippets:
            # Pre-search failed — instruct the Agent to use its own tools instead
            inject_prompt = (
                f"{_time_context()}\n\n"
                f"请使用 web_search 工具搜索：{query}\n"
                "如果 web_search 返回空，请用 code_execute 编写 Python 爬虫，"
                "向 Bing (https://www.bing.com/search?q=关键词) 或 Baidu "
                "(https://www.baidu.com/s?wd=关键词) 发送 httpx 请求，用 BeautifulSoup 解析结果。"
                "请先展示'正在搜索相关信息…'，然后调用工具，不要直接说搜不到。"
            )
        else:
            inject_prompt = (
                f"{_time_context()}\n\n"
                f"以下是网络搜索结果：\n{snippets}\n\n请基于以上信息回答：{query}"
            )
        return {
            "type": "ai",
            "skill_code": "websearch",
            "processed_content": query,
            "skill_meta": {
                "search_results": snippets,
                "inject_prompt": inject_prompt,
            },
        }

    return {
        "type": "ai",
        "skill_code": None,
        "processed_content": text,
        "skill_meta": {},
    }


async def _weather(city: str, api_key: str | None = None) -> str:
    if api_key:
        # User configured their own OWM key — use it for richer international data
        try:
            url = (
                f"https://api.openweathermap.org/data/2.5/weather"
                f"?q={urllib.parse.quote(city)}&appid={api_key}&units=metric&lang=zh_cn"
            )
            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
                r = await client.get(url)
            data = r.json()
            if r.status_code == 200:
                desc = data["weather"][0]["description"]
                temp = data["main"]["temp"]
                feels = data["main"]["feels_like"]
                humidity = data["main"]["humidity"]
                return (
                    f"🌤 **{city}天气**\n"
                    f"- 天气：{desc}\n"
                    f"- 温度：{temp}°C（体感{feels}°C）\n"
                    f"- 湿度：{humidity}%"
                )
            log_error(
                f"weather OWM status={r.status_code} body={str(data)[:300]}",
                RuntimeError(f"HTTP {r.status_code}"),
            )
            # Fall through to uapis.cn
        except Exception as exc:
            log_error(f"weather OWM city={city}", exc)
            # Fall through to uapis.cn

    # uapis.cn — free public API, Chinese native, no key required
    try:
        encoded = urllib.parse.quote(city)
        url = f"https://uapis.cn/api/v1/misc/weather?city={encoded}&extended=true"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
            r = await client.get(url)
        if r.status_code == 404:
            return f"【天气查询】未找到「{city}」的天气数据，请检查城市名称"
        if r.status_code != 200:
            log_error(
                f"weather uapis.cn HTTP {r.status_code} city={city}",
                RuntimeError(f"HTTP {r.status_code}"),
            )
            return f"【天气查询】城市：{city}\n（天气服务返回 {r.status_code}，请稍后重试）"

        data = r.json()
        weather = data.get("weather", "")
        temp = data.get("temperature", "")
        feels = data.get("feels_like", "")
        humidity = data.get("humidity", "")
        wind_dir = data.get("wind_direction", "")
        wind_power = data.get("wind_power", "")
        location = data.get("district") or data.get("city", city)
        province = data.get("province", "")

        lines = [f"🌤 **{province} {location}** 天气"]
        if weather:
            lines.append(f"- 天气：{weather}")
        if temp != "":
            feel_str = f"（体感{feels}°C）" if feels and feels != temp else ""
            lines.append(f"- 温度：{temp}°C{feel_str}")
        if humidity != "":
            lines.append(f"- 湿度：{humidity}%")
        if wind_dir or wind_power:
            wind = f"{wind_dir} {wind_power}".strip()
            lines.append(f"- 风力：{wind}")

        aqi = data.get("aqi")
        aqi_cat = data.get("aqi_category")
        if aqi is not None and aqi != "":
            aqi_str = f"（{aqi_cat}）" if aqi_cat else ""
            lines.append(f"- 空气质量：AQI {aqi}{aqi_str}")

        report_time = data.get("report_time", "")
        if report_time:
            lines.append(f"- 更新时间：{report_time}")

        return "\n".join(lines)
    except Exception as exc:
        log_error(f"weather uapis.cn city={city}", exc)
        return f"【天气查询】城市：{city}\n（天气服务暂时不可用，请稍后重试）"


def _music_html() -> str:
    """音乐搜索 — 从接口管理读取音乐 API 密钥并生成搜索卡片。

    支持两层来源：
    1. 外置源 — 管理员在接口管理中配置的第三方音乐 API（QQ音乐、网易云等）
    2. 内置源 — 无需配置即可使用的免费音乐数据 API（iTunes、MusicBrainz）
    """
    try:
        from app.models.db import get_connection

        # Query all enabled music-related API keys
        music_api_types = ("music", "music_qq", "music_netease")
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT name, api_type, endpoint FROM api_keys"
                " WHERE api_type IN (?,?,?) AND status='enabled'",
                music_api_types,
            ).fetchall()

        external_sources: list[dict[str, str]] = []
        for row in rows:
            external_sources.append(
                {
                    "name": row["name"],
                    "api_type": row["api_type"],
                    "endpoint": row["endpoint"] or "",
                }
            )

        builtin_list = (
            "<li><strong>网易云音乐 (music.chinokou.cn)</strong> — 默认源，开箱即用</li>"
            "<li><strong>iTunes Search</strong> — Apple Music 全球曲库（免费兜底）</li>"
        )

        external_html = ""
        if external_sources:
            items = "".join(
                f"<li><strong>{s['name']}</strong> ({s['api_type']})</li>"
                for s in external_sources
            )
            external_html = (
                "<p>🔌 <strong>已配置外置源：</strong></p><ul>" + items + "</ul>"
            )
        else:
            external_html = (
                "<p>💡 管理员可在 <strong>接口管理</strong> 中配置第三方音乐 API"
                "（支持 QQ音乐、网易云音乐 及自定义接口），替代默认源。</p>"
            )

        # Note: the musicSearch() JavaScript function is defined in
        # chat.html's main <script> block so it survives innerHTML
        # insertion (browsers do not execute <script> in innerHTML).

        return (
            "\U0001f3b5 **音乐搜索**\n\n"
            "请输入歌曲名称或歌手名进行搜索：\n\n"
            '<form onsubmit="event.preventDefault();musicSearch(this)" style="display:flex;gap:8px;margin:12px 0">'
            '<input type="text" name="q" placeholder="输入歌曲名或歌手..." '
            'style="flex:1;padding:8px 12px;border-radius:8px;border:1px solid var(--border);'
            'background:var(--bg-card);color:var(--text)" />'
            '<button type="submit" style="padding:8px 16px;border-radius:8px;'
            'background:linear-gradient(135deg,#6c5ce7,#a29bfe);color:#fff;border:none;cursor:pointer">'
            "\U0001f50d 搜索</button></form>"
            '<div id="musicResults" style="margin-top:8px"></div>'
            '<details style="margin-top:10px;font-size:0.85em;opacity:0.8">'
            "<summary>\U0001f4e1 数据源说明</summary>"
            + external_html
            + "<p>\U0001f193 <strong>内置源（始终可用）：</strong></p><ul>"
            + builtin_list
            + "</ul></details>"
        )
    except Exception as exc:
        from app.models.errors import log_error

        log_error("music skill init failed", exc)
        return "🎵 **音乐搜索**\n\n⚠️ 音乐服务初始化失败，请检查 API 配置。"


async def _web_search(query: str, _api_key: str | None = None) -> str:
    # Bing search (unauthenticated, works in China) with DuckDuckGo fallback
    backends = [
        ("bing", _search_bing),
        ("ddg", _search_duckduckgo),
    ]
    for name, fn in backends:
        try:
            result = await fn(query)
            if result and result != "EMPTY":
                # Validate: Bing sometimes returns anti-bot filler (wholly
                # irrelevant English results for a Chinese query).  If every
                # result block contains zero CJK characters while the query
                # does, treat it as garbage and fall through.
                if name == "bing" and _bing_results_are_garbage(result, query):
                    log_error(
                        f"_web_search {name} garbage results — falling through",
                        RuntimeError("garbage"),
                    )
                    continue
                return result
            log_error(f"_web_search {name} returned empty", RuntimeError("empty"))
        except Exception as exc:
            log_error(f"_web_search {name} failed query={query[:40]}", exc)
    return "（网络搜索暂时不可用，请稍后重试）"


def _bing_results_are_garbage(results: str, query: str) -> bool:
    """Detect Bing anti-bot filler (all-English results for a CJK query)."""
    import re

    has_cjk = bool(re.search(r"[一-鿿]", query))
    if not has_cjk:
        return False
    blocks = results.split("\n---\n")
    if not blocks:
        return False
    # If every block is CJK-free, it's almost certainly anti-bot filler
    return all(not re.search(r"[一-鿿]", b) for b in blocks)


async def _search_bing(query: str) -> str:
    """Bing web search via HTML scraping — no API key, works in China."""
    encoded = urllib.parse.quote(query)
    url = f"https://www.bing.com/search?q={encoded}&setlang=zh-cn"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(12),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
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
    for li in soup.select("li.b_algo, .b_results li, ol#b_results > li")[:6]:
        title_el = li.select_one("h2 a, .b_title a")
        snippet_el = li.select_one(".b_caption p, .b_lineclamp2, .b_algoSlug, p")
        title = title_el.get_text(strip=True) if title_el else ""
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        if title:
            results.append(f"{title}\n{snippet}" if snippet else title)
    return "\n---\n".join(results) if results else "EMPTY"


async def _search_duckduckgo(query: str) -> str:
    """DuckDuckGo Instant Answer — free, works outside China."""
    encoded = urllib.parse.quote(query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_redirect=1"
    async with httpx.AsyncClient(timeout=httpx.Timeout(5)) as client:
        r = await client.get(url, follow_redirects=True)
    data = r.json()
    results: list[str] = []
    abstract: str = data.get("AbstractText", "")
    if abstract:
        results.append(abstract)
    for topic in (data.get("RelatedTopics") or [])[:3]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append(topic["Text"])
    if results:
        return "\n".join(results)
    return "EMPTY"
