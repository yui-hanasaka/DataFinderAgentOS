"""Utility module for input validation and type conversion.

Provides safe type-conversion helpers (parse_int, parse_float,
parse_bool, parse_json_body) and URL validation utilities.
"""

from typing import Any


def parse_int(
    value: Any,
    default: int = 0,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        v = int(value)
    except (ValueError, TypeError):
        return default
    if min_value is not None and v < min_value:
        return min_value
    if max_value is not None and v > max_value:
        return max_value
    return v


def parse_float(
    value: Any,
    default: float = 0.0,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    if value is None or str(value).strip() == "":
        return default
    try:
        v = float(value)
    except (ValueError, TypeError):
        return default
    if min_value is not None and v < min_value:
        return min_value
    if max_value is not None and v > max_value:
        return max_value
    return v


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in ("1", "true", "yes", "on")


def parse_json_body(
    body: bytes, max_bytes: int = 1048576
) -> tuple[dict[str, object], str | None]:
    import json

    if len(body) > max_bytes:
        return {}, "请求体过大"
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {}, "请求体格式错误"
    if not isinstance(data, dict):
        return {}, "请求体必须是JSON对象"
    return data, None


def is_valid_url(url: str) -> bool:
    if not url:
        return False
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def is_safe_public_url(url: str) -> bool:
    if not is_valid_url(url):
        return False
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    blocked = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    if host in blocked:
        return False
    import ipaddress

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return False
    return True
