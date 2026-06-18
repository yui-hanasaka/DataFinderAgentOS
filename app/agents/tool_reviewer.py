import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.models.deep import _repair_truncated_json
from app.models.errors import log_error
from app.models.model_client import chat_complete, parse_chat_response
from app.models.model_engine import ModelRepository

_NO_REVIEW = frozenset({"env_info", "watchtower_search"})
_logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    approved: bool
    reason: str


def _build_conversation_summary(
    messages: list[dict[str, Any]], max_items: int = 6
) -> str:
    """Summarise recent conversation turns for the reviewer.

    Shows the last few assistant responses (reasoning) and tool results so the
    reviewer understands *why* the current tool call makes sense in context —
    not just the original user intent.
    """
    parts: list[str] = []
    recent = messages[-max_items:] if len(messages) > max_items else messages
    for m in recent:
        role = m.get("role", "")
        if role == "assistant":
            content = m.get("content", "")
            if content:
                parts.append(f"[AI思考] {content[:200]}")
            # Note tool calls made
            tcs = m.get("tool_calls") or []
            if tcs:
                for tc in tcs:
                    fn = tc.get("function") or {}
                    parts.append(
                        f"[AI调用工具] {fn.get('name', '')}: {fn.get('arguments', '')[:200]}"
                    )
        elif role == "tool":
            content = m.get("content", "")
            if content:
                parts.append(f"[工具结果] {content[:200]}")
    return "\n".join(parts) if parts else "（无历史上下文，这是首次工具调用）"


async def _review_once(
    user_text: str,
    tool_name: str,
    args: dict[str, Any],
    api_key: str,
    model_row: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
) -> ReviewResult:
    system = (
        "你是工具调用安全审查员。判断工具调用是否符合用户意图且安全。"
        '注意：用户意图可能比较宽泛（如"今天新闻"），而当前工具调用可能是AI多轮推理后的细化请求。'
        "请参考对话历史理解上下文，只拦截明显偏离用户意图或危险的调用。"
        '只返回JSON格式: {"approved": true/false, "reason": "简短原因"}'
    )

    context = _build_conversation_summary(messages or [])
    prompt = (
        f"用户原始意图: {user_text[:300]}\n"
        f"对话上下文:\n{context}\n"
        f"当前工具: {tool_name}\n"
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
        max_tokens=256,
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

    # Try strict parse first, fall back to JSON repair for truncated model output
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        repaired = _repair_truncated_json(content)
        try:
            result = json.loads(repaired)
        except json.JSONDecodeError:
            # Both failed — treat as denial (fail closed)
            _logger.warning(
                "tool_reviewer JSON unparseable for tool=%s, denying. "
                "raw=%s repaired=%s",
                tool_name,
                content[:200],
                repaired[:200],
            )
            return ReviewResult(approved=False, reason="审查服务异常，已拒绝执行")

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
    messages: list[dict[str, Any]] | None = None,
) -> ReviewResult:
    if tool_name in _NO_REVIEW:
        return ReviewResult(approved=True, reason="低风险工具")

    for attempt in range(2):
        try:
            return await _review_once(
                user_text, tool_name, args, api_key, model_row, messages
            )
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
