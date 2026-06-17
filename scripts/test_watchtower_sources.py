"""Parallel test script for watchtower sources — tests all enabled sources
against a keyword and reports results for auditing."""

import asyncio
import sqlite3
import sys
import time

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
sys.path.insert(0, ".")

from app.models.db import init_db
from app.models.watchtower import SourceRepository
from app.models.watchtower_scraper import WatchtowerScraper


async def test_source(src: sqlite3.Row, keyword: str, pages: int, limit: int):
    """Test a single source and return timing + results."""
    src_id = src["id"]
    name = src["name"]
    src_type = src["source_type"]
    start = time.monotonic()
    try:
        items = await WatchtowerScraper.scrape_source_async(
            src_id, keyword, pages, limit
        )
        elapsed = time.monotonic() - start
        return {
            "source_id": src_id,
            "name": name,
            "type": src_type,
            "status": "ok",
            "count": len(items),
            "elapsed_ms": round(elapsed * 1000),
            "items": items[:3],
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "source_id": src_id,
            "name": name,
            "type": src_type,
            "status": "error",
            "error": str(e)[:200],
            "count": 0,
            "elapsed_ms": round(elapsed * 1000),
            "items": [],
        }


async def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else "西华师范大学"
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    print("[Watchtower] Parallel source test")
    print(f"  Keyword: {keyword}")
    print(f"  Pages/src: {pages}, Limit/src: {limit}")
    print()

    init_db()

    sources = SourceRepository.list_all_enabled()
    if not sources:
        print("[ERROR] No enabled sources!")
        return

    print(f"  Found {len(sources)} enabled sources, running in parallel...\n")

    # Run all sources in parallel
    start_all = time.monotonic()
    tasks = [test_source(src, keyword, pages, limit) for src in sources]
    results = await asyncio.gather(*tasks)
    total_elapsed = time.monotonic() - start_all

    # Sort by count descending
    results.sort(key=lambda r: r["count"], reverse=True)

    total_items = sum(r["count"] for r in results)
    ok_sources = sum(1 for r in results if r["status"] == "ok")
    err_sources = sum(1 for r in results if r["status"] == "error")
    zero_sources = sum(1 for r in results if r["status"] == "ok" and r["count"] == 0)

    print("=" * 72)
    print("  AUDIT REPORT")
    print("=" * 72)
    print(f"  Total time: {total_elapsed:.1f}s (parallel)")
    print(f"  Total items: {total_items}")
    print(
        f"  OK sources: {ok_sources}  |  Errors: {err_sources}  |  Empty: {zero_sources}"
    )
    print()

    # Per-source detail
    for r in results:
        if r["count"] > 0:
            icon = "[OK]"
        elif r["status"] == "ok":
            icon = "[EMPTY]"
        else:
            icon = "[FAIL]"
        print(
            f"  {icon} [{r['type']:12s}] {r['name']:20s}  -> {r['count']:3d} items  ({r['elapsed_ms']:5d}ms)"
        )
        if r["status"] == "error":
            print(f"        Error: {r['error']}")
        if r["items"]:
            for item in r["items"]:
                title = (item.get("title") or "(no title)")[:70]
                print(f"        - {title}")

    # Sources by type
    print()
    print("-" * 72)
    print("  By type:")
    by_type: dict[str, int] = {}
    for r in results:
        t = r["type"]
        by_type[t] = by_type.get(t, 0) + r["count"]
    for t, c in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
        print(f"    {t:16s}: {c:4d} items")

    # Quality assessment
    print()
    print("-" * 72)
    print("  Quality assessment:")
    if total_items == 0:
        print("    [CRITICAL] All sources returned zero results!")
    elif total_items < 10:
        print(f"    [WARNING] Only {total_items} items collected — coverage too low.")
    elif total_items < 30:
        print(f"    [OK] {total_items} items — moderate coverage.")
    else:
        print(f"    [GOOD] {total_items} items — good coverage.")

    if err_sources > len(results) // 2:
        print(f"    [CRITICAL] {err_sources}/{len(results)} sources failed!")
    elif err_sources > 0:
        print(f"    [NOTE] {err_sources} source(s) failed, see errors above.")

    return results


if __name__ == "__main__":
    asyncio.run(main())
