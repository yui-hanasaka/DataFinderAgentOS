#!/usr/bin/env python3
"""Find split {% if/for %} tags — Tornado requires complete tag on one line."""

import sys
from pathlib import Path

issues = 0

for f in sorted(Path("app/templates").rglob("*.html")):
    lines = f.read_text("utf-8").splitlines()
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if "{% if " in s and "%}" not in s:
            print(f"{f}:{i}: SPLIT IF — {s[:120]}")
            issues += 1
        if "{% for " in s and "%}" not in s:
            print(f"{f}:{i}: SPLIT FOR — {s[:120]}")
            issues += 1
        # Also: }% alone on a line (continuation of prev condition)
        if s == "%}" or s.startswith("%} ") or s.startswith("%}") and len(s) <= 3:
            print(f"{f}:{i}: LONELY %}} — {s[:120]}")
            issues += 1
        # Line with just "selected{% end %}" or similar
        if (
            s.startswith("selected{% end")
            or s.startswith("disabled{% end")
            or s.startswith("%}selected")
        ):
            print(f"{f}:{i}: FRAGMENT — {s[:120]}")
            issues += 1
sys.exit(1 if issues else 0)
