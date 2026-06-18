"""Diagnostic: probe wttr.in and OpenWeatherMap responses for a city."""

import asyncio
import json
import sys
import urllib.parse

import httpx


async def probe(city: str) -> None:
    encoded = urllib.parse.quote(city)
    url = f"https://wttr.in/{encoded}?format=j1"
    print(f"→ GET {url}\n")

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15),
        headers={"Accept-Language": "zh-CN,zh;q=0.9", "User-Agent": "curl/7.88"},
        follow_redirects=True,
    ) as client:
        r = await client.get(url)

    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('content-type', '-')}\n")

    raw = r.text
    print("=== RAW (first 1000 chars) ===")
    print(raw[:1000])
    print()

    try:
        data = json.loads(raw)
        print("=== JSON OK ===")
        cur = data.get("current_condition", [{}])[0]
        print("current_condition keys:", list(cur.keys())[:15])
        print("lang_zh:", cur.get("lang_zh"))
        print("weatherDesc:", cur.get("weatherDesc"))
        print("temp_C:", cur.get("temp_C"))
        print("FeelsLikeC:", cur.get("FeelsLikeC"))
        print("humidity:", cur.get("humidity"))
        area = data.get("nearest_area", [{}])[0]
        print(
            "nearest_area:", area.get("areaName", [{}])[0].get("value") if area else "-"
        )
    except Exception as e:
        print(f"JSON parse FAILED: {e}")
        print("→ Not valid JSON (maybe HTML/text format returned)")


city = sys.argv[1] if len(sys.argv) > 1 else "南充"
asyncio.run(probe(city))
