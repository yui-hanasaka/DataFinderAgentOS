import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx


async def chat_complete(
    base_url: str,
    api_key: str,
    model_id: str,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 1024,
    stream: bool = False,
) -> httpx.Response:
    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream" if stream else "application/json",
    }
    # Don't use context manager for streaming — the client must stay alive
    # while the caller iterates the response body. httpx.AsyncClient.__aexit__
    # closes all connections, which would kill the SSE stream mid-flight.
    timeout = httpx.Timeout(120, connect=10)
    client = httpx.AsyncClient(timeout=timeout)
    resp = await client.send(
        client.build_request("POST", url, headers=headers, json=body),
        stream=stream,
    )
    if resp.status_code >= 400:
        # Read the error body and surface it as an exception
        try:
            error_body = await resp.aread()
            error_json = json.loads(error_body.decode("utf-8"))
            err_msg = error_json.get("error", {}).get("message", "") or str(error_json)
        except Exception:
            err_msg = f"HTTP {resp.status_code}"
        await client.aclose()
        raise RuntimeError(f"API error {resp.status_code}: {err_msg}")
    if not stream:
        # Read the full response before closing the client
        await resp.aread()
        await client.aclose()
    return resp


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


async def parse_chat_response_async(resp: httpx.Response) -> dict[str, str | int]:
    raw = await resp.aread() if hasattr(resp, "aread") else resp.read()
    return parse_chat_response(raw)


async def iter_sse_chunks(
    stream: httpx.Response,
) -> AsyncGenerator[dict[str, Any], None]:
    async for raw in stream.aiter_lines():
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
