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

            rev = await tool_review(user_text, name, args, api_key, model_row)
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
