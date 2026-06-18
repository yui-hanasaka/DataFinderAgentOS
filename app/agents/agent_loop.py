import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.tool_executor import execute as tool_execute
from app.agents.tool_registry import TOOLS
from app.agents.tool_reviewer import review as tool_review
from app.models.errors import log_error
from app.models.model_client import chat_complete, iter_sse_chunks
from app.models.model_engine import ModelRepository

MAX_TOOL_TURNS = 8

StreamCallback = Callable[[str, Any], Awaitable[None]]


async def _stream_chat_once(
    api_key: str,
    messages: list[dict[str, Any]],
    model_row: dict[str, Any],
    stream_cb: StreamCallback,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
    """Call chat_complete with streaming, accumulate text and tool_calls.

    Returns (full_text_content, tool_calls_list, usage_dict).
    """
    active_tools = tools if tools is not None else TOOLS
    resp = await chat_complete(
        str(model_row["base_url"]),
        api_key,
        str(model_row["model_id"]),
        messages,
        temperature=float(model_row.get("temperature") or 0.7),
        max_tokens=int(model_row.get("max_tokens") or 1024),
        stream=True,
        tools=active_tools,
    )

    full_content = ""
    tool_calls_list: list[dict[str, Any]] = []
    usage: dict[str, int] = {}

    try:
        async for chunk in iter_sse_chunks(resp):
            if "usage" in chunk:
                usage = {
                    "prompt_tokens": int(chunk["usage"].get("prompt_tokens") or 0),
                    "completion_tokens": int(
                        chunk["usage"].get("completion_tokens") or 0
                    ),
                    "total_tokens": int(chunk["usage"].get("total_tokens") or 0),
                }
            delta = ((chunk.get("choices") or [{}])[0]).get("delta") or {}
            text = delta.get("content") or ""
            if text:
                full_content += text
                await stream_cb("text", text)

            # Accumulate tool calls from streaming delta
            tc_deltas = delta.get("tool_calls") or []
            for tc in tc_deltas:
                idx: int = tc.get("index", 0)
                while len(tool_calls_list) <= idx:
                    tool_calls_list.append(
                        {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    )
                entry = tool_calls_list[idx]
                if "id" in tc:
                    entry["id"] = tc["id"]
                fn_delta = tc.get("function") or {}
                if fn_delta.get("name"):
                    entry["function"]["name"] = fn_delta["name"]
                if fn_delta.get("arguments"):
                    entry["function"]["arguments"] += fn_delta["arguments"]
    finally:
        await resp.aclose()

    # Filter out any empty tool call placeholders (no name = never filled)
    tool_calls_list = [tc for tc in tool_calls_list if tc["function"]["name"]]

    return full_content, tool_calls_list, usage


async def run(
    user_text: str,
    messages: list[dict[str, Any]],
    model_row: dict[str, Any],
    stream_cb: StreamCallback,
    allowed_tools: list[str] | None = None,
) -> str:
    """
    Run the agentic loop.

    stream_cb(event_type, data):
        "text"        -> str  (text chunk to show user)
        "tool_call"   -> dict {name, args, call_id}
        "tool_review" -> dict {name, approved, reason, call_id}
        "tool_result" -> dict {name, content, call_id}

    Returns the full text reply.
    """
    # Inject time context + web scraping guidance for tool-use awareness
    from app.models.skill_dispatcher import _time_context

    search_guidance = (
        "【搜索策略 — 重要】web_search 工具可能因反爬虫机制返回空结果。"
        "当你发现 web_search 返回空或失败时，请直接用 code_execute 编写 Python 爬虫：\n"
        "1. **直接向搜索引擎官网发请求**：用 httpx 构造搜索URL并请求，"
        "示例 — Bing: https://www.bing.com/search?q=关键词, "
        "Baidu: https://www.baidu.com/s?wd=关键词, "
        "DuckDuckGo: https://html.duckduckgo.com/html/?q=关键词\n"
        "2. **解析搜索结果**：用 BeautifulSoup 提取标题、摘要、链接，返回结构化数据\n"
        "3. **抓取具体网页**：先用 web_fetch 下载目标 URL 的 HTML 到工作区，"
        "再用 code_execute + BeautifulSoup 解析提取正文内容\n"
        "4. httpx 已预配置 Edge UA 和中文 Accept-Language，可绕过大部分反爬；"
        "如需更高级的反反爬（Cookie、Referer、延迟），可在代码中自行设置\n"
        "5. 文件保存在工作区目录，跨轮次持久化，可逐步处理大型网站"
    )
    time_msg = {
        "role": "system",
        "content": _time_context() + "\n\n" + search_guidance,
    }
    if messages and messages[0]["role"] == "system":
        messages.insert(1, time_msg)
    else:
        messages.insert(0, time_msg)

    # Filter tools based on employee's allowed_tools
    active_tools = TOOLS
    if allowed_tools is not None:
        active_tools = [t for t in TOOLS if t["function"]["name"] in allowed_tools]

    # model_row["api_key"] is already decrypted by ModelRepository
    api_key: str = str(model_row["api_key"])
    if not api_key:
        err = "模型 API Key 未设置或已失效（服务器重启后加密密钥可能变更）。请联系管理员更新模型配置。"
        await stream_cb("text", err)
        return err

    for _turn in range(MAX_TOOL_TURNS):
        full_content = ""
        calls: list[dict[str, Any]] = []

        for attempt in range(2):
            try:
                full_content, calls, usage = await _stream_chat_once(
                    api_key, messages, model_row, stream_cb, tools=active_tools
                )
                if usage.get("total_tokens"):
                    ModelRepository.record_usage(
                        int(model_row["id"]),
                        int(usage.get("prompt_tokens") or 0),
                        int(usage.get("completion_tokens") or 0),
                    )
                break
            except Exception as exc:
                if attempt == 0:
                    log_error("agent_loop chat_complete (attempt 1, will retry)", exc)
                    await asyncio.sleep(1.0)
                else:
                    log_error("agent_loop chat_complete (attempt 2, giving up)", exc)
                    err = "模型调用失败，请稍后重试"
                    await stream_cb("text", err)
                    return err

        if not calls:
            return full_content

        messages.append(
            {
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": calls,
            }
        )

        for call in calls:
            call_id: str = call.get("id", "")
            fn = call.get("function") or {}
            name: str = fn.get("name", "")
            try:
                args: dict[str, Any] = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            await stream_cb(
                "tool_call", {"name": name, "args": args, "call_id": call_id}
            )

            rev = await tool_review(user_text, name, args, api_key, model_row, messages)
            await stream_cb(
                "tool_review",
                {
                    "name": name,
                    "approved": rev.approved,
                    "reason": rev.reason,
                    "call_id": call_id,
                },
            )

            if rev.approved:
                try:
                    result = await tool_execute(name, args)
                except Exception as exc:
                    log_error(f"agent_loop tool_execute {name}", exc)
                    result = f"工具执行失败: {exc}"
            else:
                result = f"工具调用已拒绝: {rev.reason}"

            # music_play returns audio base64 — emit as music_audio event
            # so the frontend can decode and play (bypasses markdown)
            if name == "music_play" and rev.approved:
                try:
                    data = json.loads(result)
                    audio_b64 = data.get("audio_base64", "")
                    if audio_b64:
                        await stream_cb(
                            "music_audio",
                            {
                                "song_id": data.get("song_id"),
                                "title": data.get("title", ""),
                                "artist": data.get("artist", ""),
                                "cover_url": data.get("cover_url", ""),
                                "base64": audio_b64,
                                "format": data.get("format", "mp3"),
                                "size_bytes": data.get("size_bytes", 0),
                            },
                        )
                        # Remove base64 payload to avoid cluttering tool card logs / LLM context
                        clean_data = dict(data)
                        clean_data.pop("audio_base64", None)
                        result = json.dumps(clean_data, ensure_ascii=False)
                except (json.JSONDecodeError, Exception):
                    pass

            await stream_cb(
                "tool_result",
                {"name": name, "content": result, "call_id": call_id},
            )

            messages.append(
                {"role": "tool", "tool_call_id": call_id, "content": result}
            )

    final = "（工具调用轮次已达上限）"
    await stream_cb("text", final)
    return final
