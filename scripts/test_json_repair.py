"""Quick smoke tests for _extract_json_from_model_output and _repair_truncated_json."""

import json
import sys

sys.path.insert(0, ".")
from app.models.deep import _extract_json_from_model_output  # noqa: E402

FAILURES = 0


def expect_parses(label: str, raw: str, expected_summary: str | None = None) -> None:
    global FAILURES
    try:
        cleaned = _extract_json_from_model_output(raw)
        parsed = json.loads(cleaned)
        assert isinstance(parsed, dict), f"expected dict, got {type(parsed)}"
        if expected_summary is not None:
            assert parsed.get("summary") == expected_summary, (
                f"summary mismatch: {parsed.get('summary')!r}"
            )
        print(f"  PASS: {label}")
    except Exception as exc:
        FAILURES += 1
        print(f"  FAIL: {label} — {exc}")


print("Test: _extract_json_from_model_output")

# 1) valid JSON passes through
expect_parses(
    "valid JSON",
    '{"summary": "hello", "keywords": ["a"], "sentiment": "neutral", "risk": 0, "markdown": ""}',
    "hello",
)

# 2) ```json fenced block
expect_parses(
    "```json fence",
    '```json\n{"summary": "fenced", "keywords": [], "sentiment": "neutral", "risk": 0, "markdown": ""}\n```',
    "fenced",
)

# 3) ``` fence without language tag
expect_parses(
    "``` fence no lang",
    '```\n{"summary": "no-lang", "keywords": [], "sentiment": "neutral", "risk": 0, "markdown": ""}\n```',
    "no-lang",
)

# 4) truncated mid-string (the actual bug scenario)
# The repair closes the unclosed string + object → JSON parses successfully
truncated_mid_string = (
    '{\n    "summary": "该早报汇总了多条科技新闻：大疆发布Osmo Pocket 4P双主摄口袋电影机，'
    "定价3799元；Linux Kernel 7.1正式版发布，提升稳定性并支持AMD Zen 6；Koss推出开放式头戴耳机A/55"
)
expect_parses("truncated mid-string", truncated_mid_string)

# 5) leading preamble text
expect_parses(
    "leading text",
    'Sure! Here is the JSON:\n{"summary": "preamble", "keywords": [], "sentiment": "neutral", "risk": 0, "markdown": ""}',
    "preamble",
)

# 6) completely empty
expect_parses("empty string", "")

print(f"\nDone — {FAILURES} failure(s)")
sys.exit(FAILURES)
