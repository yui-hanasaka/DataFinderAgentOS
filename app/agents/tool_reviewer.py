import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.models.errors import log_error
from app.models.model_client import chat_complete, parse_chat_response
from app.models.model_engine import ModelRepository

_NO_REVIEW = frozenset({"env_info", "watchtower_search"})
_logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    approved: bool
    reason: str


async def _review_once(
    user_text: str,
    tool_name: str,
    args: dict[str, Any],
    api_key: str,
    model_row: dict[str, Any],
) -> ReviewResult:
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
    prompt_tokens = int(parsed.get("prompt_tokens") or 0)
    completion_tokens = int(parsed.get("completion_tokens") or 0)
    if prompt_tokens or completion_tokens:
        ModelRepository.record_usage(
            int(model_row["id"]),
            prompt_tokens,
            completion_tokens,
        )
    content = str(parsed.get("content", "")).strip()
    content = (
        content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )
    result = json.loads(content)
    return ReviewResult(
        approved=bool(result.get("approved", True)),
        reason=str(result.get("reason", "")),
    )


async def review(
    user_text: str,
    tool_name: str,
    args: dict[str, Any],
    api_key: str,
    model_row: dict[str, Any],
) -> ReviewResult:
    if tool_name in _NO_REVIEW:
        return ReviewResult(approved=True, reason="低风险工具")

    for attempt in range(2):
        try:
            return await _review_once(user_text, tool_name, args, api_key, model_row)
        except Exception as exc:
            if attempt == 0:
                log_error(f"tool_reviewer: {tool_name} (attempt 1, will retry)", exc)
                await asyncio.sleep(1.0)
            else:
                log_error(
                    f"tool_reviewer: {tool_name} (attempt 2, failing closed)", exc
                )
                _logger.warning(
                    "tool_reviewer failed for tool=%s after 2 attempts, failing CLOSED (denied)",
                    tool_name,
                )
                return ReviewResult(
                    approved=False, reason="审查服务暂时不可用，已拒绝执行"
                )
    return ReviewResult(approved=False, reason="审查服务不可用")
