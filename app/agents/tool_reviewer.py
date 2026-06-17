import json
from dataclasses import dataclass
from typing import Any

from app.models.errors import log_error
from app.models.model_client import chat_complete, parse_chat_response

_NO_REVIEW = frozenset({"env_info", "watchtower_search"})


@dataclass
class ReviewResult:
    approved: bool
    reason: str


async def review(
    user_text: str,
    tool_name: str,
    args: dict[str, Any],
    api_key: str,
    model_row: dict[str, Any],
) -> ReviewResult:
    if tool_name in _NO_REVIEW:
        return ReviewResult(approved=True, reason="低风险工具")

    system = (
        "你是工具调用安全审查员。判断工具调用是否符合用户意图且安全。"
        '只返回JSON格式: {"approved": true/false, "reason": "简短原因"}'
    )
    prompt = (
        f"用户意图: {user_text[:300]}\n"
        f"工具名称: {tool_name}\n"
        f"调用参数: {json.dumps(args, ensure_ascii=False)[:500]}\n"
        "请审查并返回JSON。"
    )

    try:
        resp = await chat_complete(
            str(model_row["base_url"]),
            api_key,
            str(model_row["model_id"]),
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=150,
            stream=False,
        )
        parsed = parse_chat_response(resp.content)
        content = str(parsed.get("content", "")).strip()
        content = (
            content.removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        result = json.loads(content)
        return ReviewResult(
            approved=bool(result.get("approved", True)),
            reason=str(result.get("reason", "")),
        )
    except Exception as exc:
        log_error(f"tool_reviewer: {tool_name}", exc)
        return ReviewResult(approved=True, reason="审查服务暂时不可用")
