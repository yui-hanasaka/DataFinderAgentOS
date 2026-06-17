import asyncio
import atexit
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 2
_RETRY_DELAYS = [1.0, 2.0]

_shared_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
        timeout = httpx.Timeout(120, connect=10)
        _shared_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    return _shared_client


async def close_shared_client() -> None:
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None


def _cleanup() -> None:
    """Best-effort sync cleanup for atexit."""
    try:
        asyncio.run(close_shared_client())
    except Exception:
        pass


atexit.register(_cleanup)


async def chat_complete(
    base_url: str,
    api_key: str,
    model_id: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 1024,
    stream: bool = False,
    tools: list[dict[str, Any]] | None = None,
) -> httpx.Response:
    url = base_url.rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max(1, min(max_tokens, 393216)),
        "stream": stream,
    }
    if tools is not None:
        body["tools"] = tools
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream" if stream else "application/json",
    }

    client = _get_client()
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = await client.send(
                client.build_request("POST", url, headers=headers, json=body),
                stream=stream,
            )
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_DELAYS[attempt]
                logger.debug(
                    "Connection error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                continue
            raise

        if resp.status_code >= 400:
            try:
                error_body = await resp.aread()
                error_json = json.loads(error_body.decode("utf-8"))
                err_msg = error_json.get("error", {}).get("message", "") or str(
                    error_json
                )
            except Exception:
                err_msg = f"HTTP {resp.status_code}"

            if resp.status_code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
                delay = _RETRY_DELAYS[attempt]
                logger.debug(
                    "Retryable HTTP %d (attempt %d/%d), retrying in %.1fs",
                    resp.status_code,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            raise RuntimeError(f"API error {resp.status_code}: {err_msg}")

        # Success
        if not stream:
            await resp.aread()
        # Shared client persists across calls — callers must NOT close it
        return resp

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Unexpected retry exhaustion")


def parse_chat_response(raw_bytes: bytes) -> dict[str, str | int]:
    payload = json.loads(raw_bytes.decode("utf-8"))
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = payload.get("usage") or {}
    return {
        "content": message.get("content") or "",
        "reasoning": message.get("reasoning_content") or "",
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def parse_tool_calls(raw_bytes: bytes) -> list[dict[str, Any]]:
    payload = json.loads(raw_bytes.decode("utf-8"))
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return list(message.get("tool_calls") or [])


async def parse_chat_response_async(resp: httpx.Response) -> dict[str, str | int]:
    raw = await resp.aread()
    return parse_chat_response(raw)


async def iter_sse_chunks(
    stream: httpx.Response,
    timeout: float | None = 120.0,
) -> AsyncGenerator[dict[str, Any], None]:
    ait = stream.aiter_lines()
    while True:
        try:
            if timeout is not None:
                raw = await asyncio.wait_for(ait.__anext__(), timeout=timeout)
            else:
                raw = await ait.__anext__()
        except StopAsyncIteration:
            break
        except asyncio.TimeoutError:
            break
        line = raw.strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        yield data
