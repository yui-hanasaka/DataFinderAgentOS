import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.tool_executor import execute as tool_execute
from app.agents.tool_registry import TOOLS
from app.agents.tool_reviewer import review as tool_review
from app.models.errors import log_error
from app.models.model_client import chat_complete, parse_chat_response, parse_tool_calls

MAX_TOOL_TURNS = 8

StreamCallback = Callable[[str, Any], Awaitable[None]]


async def run(
    user_text: str,
    messages: list[dict[str, Any]],
    model_row: dict[str, Any],
    stream_cb: StreamCallback,
) -> str:
    """
    Run the agentic loop.

    stream_cb(event_type, data):
        "text"        -> str  (text chunk to show user)
        "tool_call"   -> dict {name, args, id}
        "tool_review" -> dict {name, approved, reason}
        "tool_result" -> dict {name, result, id}

    Returns the full text reply.
    """
    from app.models.secrets_store import decrypt

    api_key: str = decrypt(str(model_row["api_key"]))

    for _turn in range(MAX_TOOL_TURNS):
        try:
            resp = await chat_complete(
                str(model_row["base_url"]),
                api_key,
                str(model_row["model_id"]),
                messages,
                temperature=float(model_row.get("temperature") or 0.7),
                max_tokens=int(model_row.get("max_tokens") or 1024),
                stream=False,
                tools=TOOLS,
            )
        except Exception as exc:
            log_error("agent_loop chat_complete", exc)
            err = "模型调用失败，请稍后重试"
            await stream_cb("text", err)
            return err

        calls = parse_tool_calls(resp.content)
        parsed = parse_chat_response(resp.content)

        if not calls:
            text = str(parsed.get("content") or "")
            chunk_size = 60
            for i in range(0, max(len(text), 1), chunk_size):
                await stream_cb("text", text[i : i + chunk_size])
            return text

        messages.append(
            {
                "role": "assistant",
                "content": parsed.get("content") or None,
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

            await stream_cb("tool_call", {"name": name, "args": args, "id": call_id})

            rev = await tool_review(user_text, name, args, api_key, model_row)
            await stream_cb(
                "tool_review",
                {"name": name, "approved": rev.approved, "reason": rev.reason},
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
                "tool_result", {"name": name, "result": result, "id": call_id}
            )
            messages.append(
                {"role": "tool", "tool_call_id": call_id, "content": result}
            )

    final = "（工具调用轮次已达上限）"
    await stream_cb("text", final)
    return final
