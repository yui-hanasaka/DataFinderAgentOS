import re
import urllib.parse
from typing import Any

import httpx

from app.models.errors import log_error

DispatchResult = dict[str, Any]


async def dispatch(text: str, api_keys: dict[str, str] | None = None) -> DispatchResult:
    keys = api_keys or {}

    m = re.match(r"^@(?:weather|天气)\s+(.+)", text.strip(), re.IGNORECASE)
    if m:
        city = m.group(1).strip()
        result = await _weather(city, keys.get("weather"))
        return {
            "type": "skill",
            "skill_code": "weather",
            "processed_content": result,
            "skill_meta": {"city": city},
        }

    if re.match(r"^@(?:music|音乐)\b", text.strip(), re.IGNORECASE):
        return {
            "type": "skill",
            "skill_code": "music",
            "processed_content": _music_html(),
            "skill_meta": {},
        }

    m = re.match(r"^@西师妹\s*(.*)", text.strip())
    if m:
        question = m.group(1).strip()
        return {
            "type": "ai",
            "skill_code": "campus",
            "processed_content": question,
            "skill_meta": {
                "system_override": "你是西南师范大学的校园助手「西师妹」，请用友好活泼的语气回答校园相关问题。"
            },
        }

    m = re.match(r"^\\(?:search|搜索)\w*\s+(.*)", text.strip(), re.IGNORECASE)
    if m:
        query = m.group(1).strip()
        snippets = await _web_search(query, keys.get("websearch"))
        return {
            "type": "ai",
            "skill_code": "websearch",
            "processed_content": query,
            "skill_meta": {
                "search_results": snippets,
                "inject_prompt": f"以下是网络搜索结果：\n{snippets}\n\n请基于以上信息回答：{query}",
            },
        }

    return {
        "type": "ai",
        "skill_code": None,
        "processed_content": text,
        "skill_meta": {},
    }


# wttr.in weather code → Chinese description (WW Online codes)
_WEATHER_CODES_ZH: dict[str, str] = {
    "113": "晴",
    "116": "多云",
    "119": "多云",
    "122": "阴",
    "143": "雾",
    "176": "小雨",
    "179": "小雪",
    "182": "雨夹雪",
    "185": "冻雨",
    "200": "雷阵雨",
    "227": "暴风雪",
    "230": "暴风雪",
    "248": "雾",
    "260": "雾",
    "263": "小雨",
    "266": "小雨",
    "281": "冻雨",
    "284": "冻雨",
    "293": "小雨",
    "296": "小雨",
    "299": "中雨",
    "302": "中雨",
    "305": "大雨",
    "308": "大雨",
    "311": "冻雨",
    "314": "冻雨",
    "317": "雨夹雪",
    "320": "雨夹雪",
    "323": "小雪",
    "326": "小雪",
    "329": "中雪",
    "332": "中雪",
    "335": "大雪",
    "338": "大雪",
    "350": "冰雹",
    "353": "阵雨",
    "356": "大雨",
    "359": "暴雨",
    "362": "雨夹雪",
    "365": "雨夹雪",
    "368": "小雪",
    "371": "大雪",
    "374": "冰雹",
    "377": "冰雹",
    "386": "雷阵雨",
    "389": "雷暴",
    "392": "雷暴伴雪",
    "395": "大雪",
}


async def _weather(city: str, api_key: str | None = None) -> str:
    if api_key:
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
                f"weather OpenWeatherMap status={r.status_code} body={str(data)[:300]}"
            )
            # Fall through to wttr.in
        except Exception as exc:
            log_error(f"weather OpenWeatherMap city={city}", exc)
            # Fall through to wttr.in

    # wttr.in — free, no API key, JSON API
    try:
        encoded = urllib.parse.quote(city)
        url = f"https://wttr.in/{encoded}?format=j1"
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12),
            headers={"User-Agent": "curl/7.88", "Accept-Language": "zh-CN,zh;q=0.9"},
        ) as client:
            r = await client.get(url, follow_redirects=True)
        if r.status_code != 200:
            log_error(f"weather wttr.in HTTP {r.status_code} city={city}")
            return f"【天气查询】城市：{city}\n（天气服务返回 {r.status_code}，请稍后重试）"

        data = r.json()
        cur = data["current_condition"][0]
        code = cur.get("weatherCode", "")
        desc = _WEATHER_CODES_ZH.get(
            str(code), cur.get("weatherDesc", [{}])[0].get("value", "")
        )
        temp = cur["temp_C"]
        feels = cur["FeelsLikeC"]
        humidity = cur["humidity"]
        wind = cur["windspeedKmph"]
        area = data.get("nearest_area", [{}])[0]
        area_name = area.get("areaName", [{}])[0].get("value", city) if area else city
        return (
            f"🌤 **{area_name}天气**（via wttr.in）\n"
            f"- 天气：{desc}\n"
            f"- 温度：{temp}°C（体感{feels}°C）\n"
            f"- 湿度：{humidity}%\n"
            f"- 风速：{wind} km/h"
        )
    except Exception as exc:
        log_error(f"weather wttr.in city={city}", exc)
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
            "<li><strong>iTunes Search</strong> — Apple Music 全球曲库（免费，无需密钥）</li>"
            "<li><strong>MusicBrainz</strong> — 开源音乐元数据库（免费，无需密钥）</li>"
            "<li><strong>DuckDuckGo</strong> — 网络音乐搜索（免费，无需密钥）</li>"
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
                "（支持 QQ音乐、网易云音乐 及自定义接口）。</p>"
            )

        # Note: the musicSearch() JavaScript function is defined in
        # chat.html's main <script> block so it survives innerHTML
        # insertion (browsers do not execute <script> in innerHTML).

        return (
            "\U0001f3b5 **音乐搜索**\n\n"
            "请输入歌曲名称或歌手名进行搜索：\n\n"
            '<form onsubmit="return musicSearch(this)" style="display:flex;gap:8px;margin:12px 0">'
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
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_redirect=1"
        async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
            r = await client.get(url, follow_redirects=True)
        data = r.json()
        abstract: str = data.get("AbstractText", "")
        results: list[str] = []
        if abstract:
            results.append(abstract)
        for topic in (data.get("RelatedTopics") or [])[:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(topic["Text"])
        if results:
            return "\n".join(results)
        return f"（搜索「{query}」未找到直接结果，请尝试更换关键词）"
    except Exception as exc:
        log_error(f"web search request failed for query={query}", exc)
        return "（网络搜索暂时不可用，请稍后重试）"
