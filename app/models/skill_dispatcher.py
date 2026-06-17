import re
import urllib.parse
from typing import Any

import httpx

DispatchResult = dict[str, Any]


async def dispatch(text: str, api_keys: dict[str, str] | None = None) -> DispatchResult:
    keys = api_keys or {}

    m = re.match(r"^@weather\s+(.+)", text.strip(), re.IGNORECASE)
    if m:
        city = m.group(1).strip()
        result = await _weather(city, keys.get("weather"))
        return {
            "type": "skill",
            "skill_code": "weather",
            "processed_content": result,
            "skill_meta": {"city": city},
        }

    if re.match(r"^@music\b", text.strip(), re.IGNORECASE):
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

    m = re.match(r"^\\search\w*\s+(.*)", text.strip(), re.IGNORECASE)
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


async def _weather(city: str, api_key: str | None = None) -> str:
    if not api_key:
        return f"【天气查询】城市：{city}\n（未配置天气API Key，请在接口管理中配置 weather 类型的 API Key）"
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=zh_cn"
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
            r = await client.get(url)
        data = r.json()
        if r.status_code == 200:
            desc = data["weather"][0]["description"]
            temp = data["main"]["temp"]
            feels = data["main"]["feels_like"]
            humidity = data["main"]["humidity"]
            return f"🌤 **{city}天气**\n- 天气：{desc}\n- 温度：{temp}°C（体感{feels}°C）\n- 湿度：{humidity}%"
        return (
            f"【天气查询】无法获取 {city} 的天气信息：{data.get('message', '未知错误')}"
        )
    except Exception:
        return "【天气查询】请求失败，请稍后重试"


def _music_html() -> str:
    return (
        "🎵 **音乐播放器**\n请输入歌曲名称搜索（功能开发中，可在接口管理配置音乐API）。"
    )


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
    except Exception:
        return "（网络搜索暂时不可用，请稍后重试）"
