#!/usr/bin/env python3
"""Fix split {% if/for/elif %} tags — Tornado requires complete tag on one line.

Each split tag like:
    {% if x and
        y %}
becomes:
    {% if x and y %}

The join preserves everything after the closing %} on the continuation line.
"""

import sys
import re
from pathlib import Path

TEMPLATE_DIR = Path("app/templates")

OPEN_TAG = re.compile(r"\{\%\s*(if|for|elif|end)\b")


def fix_file(filepath: Path) -> bool:
    lines = filepath.read_text("utf-8").splitlines()
    changed = False
    del_markers: set[int] = set()

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        m = OPEN_TAG.search(s)
        if m and "%}" not in s:
            # Split tag — find the closing %}
            accum = line.rstrip()
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                accum += " " + nxt.strip()
                if "%}" in nxt:
                    lines[i] = accum
                    for k in range(i + 1, j + 1):
                        del_markers.add(k)
                    changed = True
                    break
                j += 1
            i = j
        i += 1

    if changed:
        result = [line for idx, line in enumerate(lines) if idx not in del_markers]
        content = "\n".join(result)
        if not content.endswith("\n"):
            content += "\n"
        filepath.write_text(content, "utf-8")
        print(f"  FIXED {filepath}")
        return True
    return False


def main() -> int:
    total = 0
    for html_file in sorted(TEMPLATE_DIR.rglob("*.html")):
        if fix_file(html_file):
            total += 1
    print(f"\nFixed {total} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
