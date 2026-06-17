#!/usr/bin/env python3
"""Template syntax checker — catches Tornado template bugs that linters miss.

Only checks unambiguous bugs:
  1. {{ with space between braces (= Tornado won't parse as expression)
  2. [" key"] — space inside bracket-access key (sqlite3.Row won't find it)
  3. Split {% tags %}: {% if/for/end %} spanning multiple lines (Tornado rejects)
  4. Known-dangerous patterns
"""

import sys
import re
from pathlib import Path

TEMPLATE_DIR = Path("app/templates")
SPLIT_TAG = re.compile(
    r"\{\%\s*(if|for|elif|end|module|set|try|except|while|break|continue|apply|autoescape|block|comment|raw|include)\b"
)


def check_file(filepath: Path) -> list[str]:
    issues: list[str] = []
    lines = filepath.read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # { {word — space between two opening braces before a Tornado expression
        # Matches: { { stats, { { model[   but NOT: { { }  or CSS selectors
        m = re.search(r"\{\s+\{[a-zA-Z_]", stripped)
        if m:
            issues.append(
                f"{filepath}:{i}:  '{{{{' has space between braces — "
                f"Tornado won't parse this as expression"
            )

        # {{ expr } } — space before closing braces (only when preceded by Tornado-open)
        m = re.search(r"(\{\{.*?\}\s+\})(?![\{'])", stripped)
        if m:
            issues.append(
                f"{filepath}:{i}:  '}}}}' has space between braces — "
                f"Tornado won't parse this as expression"
            )

        # [" key"] — space between bracket and key (e.g. row[" id"])
        # This always results in IndexError at runtime with sqlite3.Row
        m = re.search(r'\["\s+(\w+)\s*"\]', stripped)
        if m:
            issues.append(
                f"{filepath}:{i}:  bracket access has space in key: "
                f'[" {m.group(1)}"] — should be ["{m.group(1)}"]'
            )

        # Split {% tag %} — must be on one line (causes SyntaxError)
        if SPLIT_TAG.search(stripped) and "%}" not in stripped:
            issues.append(
                f"{filepath}:{i}:  split {{% tag %}} — "
                f"Tornado requires complete tag on one line"
            )

    return issues


def main() -> int:
    all_issues: list[str] = []
    for html_file in sorted(TEMPLATE_DIR.rglob("*.html")):
        all_issues.extend(check_file(html_file))

    if all_issues:
        print(f"\n{'=' * 60}")
        print(f"  Template check: {len(all_issues)} issue(s) found")
        print(f"{'=' * 60}")
        for issue in all_issues:
            print(f"  x {issue}")
        print(f"{'=' * 60}\n")
        return 1

    print("Template check: all clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
