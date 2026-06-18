import json
import math

import tornado.web

from app.controllers.admin import AdminBaseHandler
from app.models.chat import ChatRepository
from app.models.db import get_connection


class AdminScreenHandler(AdminBaseHandler):
    def get(self) -> None:
        stats = _collect_stats()
        self.render(
            "admin/screen.html",
            title="数智大屏",
            username=self.current_user,
            stats=stats,
            stats_json=json.dumps(stats, ensure_ascii=False),
        )


class ScreenDataApiHandler(AdminBaseHandler):
    def get(self) -> None:
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(_collect_stats(), ensure_ascii=False))


class ScreenGlobeDataHandler(AdminBaseHandler):
    """GET /admin/screen/data/globe — geo-relevant watchtower data for 3D globe."""

    def get(self) -> None:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT id, title, url, sentiment, risk, published_at
                   FROM watchtower_items
                   WHERE url IS NOT NULL AND url != ''
                   ORDER BY id DESC
                   LIMIT 120"""
            ).fetchall()

        points: list[dict[str, object]] = []
        for i, r in enumerate(rows):
            # Spread points across the globe pseudo-randomly based on id
            seed = r["id"] * 2654435761 & 0xFFFFFFFF
            lat = (seed % 180) - 90 + (math.sin(i * 0.7) * 15)
            lng = ((seed // 180) % 360) - 180 + (math.cos(i * 0.7) * 15)
            lat = max(-85, min(85, lat))
            lng = max(-175, min(175, lng))
            risk = int(r["risk"]) if r["risk"] else 0
            points.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "url": r["url"],
                    "sentiment": r["sentiment"] or "未分析",
                    "risk": risk,
                    "lat": round(lat, 4),
                    "lng": round(lng, 4),
                }
            )

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"points": points}, ensure_ascii=False))


class ScreenWordCloudDataHandler(AdminBaseHandler):
    """GET /admin/screen/data/wordcloud — keyword frequency for wordcloud."""

    def get(self) -> None:
        import re

        with get_connection() as conn:
            wi_rows = conn.execute(
                "SELECT keywords FROM watchtower_items WHERE keywords != '[]' ORDER BY id DESC LIMIT 500"
            ).fetchall()
            dc_rows = conn.execute(
                "SELECT keywords FROM deep_contents WHERE keywords != '[]' ORDER BY id DESC LIMIT 500"
            ).fetchall()
            titles_rows = conn.execute(
                "SELECT title FROM watchtower_items ORDER BY id DESC LIMIT 200"
            ).fetchall()

        word_freq: dict[str, int] = {}
        for row in wi_rows:
            try:
                kws = json.loads(row["keywords"])
                if isinstance(kws, list):
                    for kw in kws:
                        if isinstance(kw, str) and len(kw) >= 2:
                            word_freq[kw] = word_freq.get(kw, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        for row in dc_rows:
            try:
                kws = json.loads(row["keywords"])
                if isinstance(kws, list):
                    for kw in kws:
                        if isinstance(kw, str) and len(kw) >= 2:
                            word_freq[kw] = word_freq.get(kw, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        for t in titles_rows:
            words = re.findall(r"[一-鿿]{2,6}|[a-zA-Z]{3,}", t["title"])
            for w in words:
                word_freq[w] = word_freq.get(w, 0) + 1

        hot_words = sorted(word_freq.items(), key=lambda x: -x[1])[:80]

        self.set_header("Content-Type", "application/json")
        self.write(
            json.dumps(
                {"words": [{"name": w, "value": c} for w, c in hot_words]},
                ensure_ascii=False,
            )
        )


def _collect_stats() -> dict[str, object]:
    with get_connection() as conn:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        msg_count = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        item_count = conn.execute("SELECT COUNT(*) FROM watchtower_items").fetchone()[0]
        # Last 7 days message trend
        trend_rows = conn.execute(
            """SELECT date(created_at) d, COUNT(*) c FROM chat_messages
               WHERE created_at >= date('now','-6 days')
               GROUP BY d ORDER BY d"""
        ).fetchall()
        # Sentiment distribution — include both watchtower_items and deep_contents
        sent_rows = conn.execute(
            """SELECT COALESCE(sentiment,'未分析') s, COUNT(*) c
               FROM (
                   SELECT sentiment FROM watchtower_items
                   UNION ALL
                   SELECT sentiment FROM deep_contents WHERE sentiment IS NOT NULL
               )
               GROUP BY s ORDER BY c DESC"""
        ).fetchall()
        # Hot words from watchtower titles (for initial page load)
        titles = conn.execute(
            "SELECT title FROM watchtower_items ORDER BY id DESC LIMIT 200"
        ).fetchall()

    session_count = ChatRepository.count_all_sessions()

    msg_trend = [{"date": r["d"], "count": r["c"]} for r in trend_rows]
    sentiment_dist = [{"name": r["s"], "value": r["c"]} for r in sent_rows]

    # Simple word frequency for hot words
    import re

    word_freq: dict[str, int] = {}
    for t in titles:
        words = re.findall(r"[一-鿿]{2,6}|[a-zA-Z]{3,}", t["title"])
        for w in words:
            word_freq[w] = word_freq.get(w, 0) + 1
    hot_words = sorted(word_freq.items(), key=lambda x: -x[1])[:60]

    return {
        "user_count": user_count,
        "session_count": session_count,
        "msg_count": msg_count,
        "item_count": item_count,
        "msg_trend": msg_trend,
        "sentiment_dist": sentiment_dist,
        "hot_words": [{"name": w, "value": c} for w, c in hot_words],
    }


class BaiduLinkRedirectHandler(tornado.web.RequestHandler):
    """Handler to redirect local 404 relative Baidu /link?url=... urls back to www.baidu.com"""

    def get(self) -> None:
        uri = self.request.uri or ""
        target_url = "https://www.baidu.com" + uri
        self.redirect(target_url)
