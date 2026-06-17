import json
import urllib.request


def chat_complete(base_url: str, api_key: str, model_id: str, messages, temperature: float = 0.7,
				 max_tokens: int = 1024, stream: bool = False):
	url = base_url.rstrip("/") + "/chat/completions"
	body = {
		"model": model_id,
		"messages": messages,
		"temperature": temperature,
		"max_tokens": max_tokens,
		"stream": stream,
	}
	data = json.dumps(body).encode("utf-8")
	req = urllib.request.Request(url, data=data, method="POST")
	req.add_header("Content-Type", "application/json")
	req.add_header("Authorization", f"Bearer {api_key}")
	req.add_header("Accept", "text/event-stream" if stream else "application/json")
	return urllib.request.urlopen(req, timeout=60)


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


def iter_sse_chunks(stream):
	for raw in stream:
		line = raw.decode("utf-8", errors="ignore").strip()
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
