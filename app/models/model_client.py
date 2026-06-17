import json

import httpx


async def chat_complete(
    base_url: str,
    api_key: str,
    model_id: str,
    messages,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    stream: bool = False,
):
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
    # Use a shared client or create per request — per request is safer for now
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as client:
        if stream:
            return await client.send(
                client.build_request("POST", url, headers=headers, json=body),
                stream=True,
            )
        return await client.post(url, headers=headers, json=body)


def parse_chat_response(raw_bytes: bytes):
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


async def parse_chat_response_async(resp):
    raw = await resp.aread() if hasattr(resp, "aread") else resp.read()
    return parse_chat_response(raw)


async def iter_sse_chunks(stream):
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
