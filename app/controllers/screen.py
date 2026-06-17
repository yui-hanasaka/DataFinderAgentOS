import json

from app.controllers.admin import AdminBaseHandler
from app.models.chat import ChatRepository
from app.models.db import get_connection


class AdminScreenHandler(AdminBaseHandler):
    def get(self):
        stats = _collect_stats()
        self.render(
            "admin/screen.html",
            title="数智大屏",
            username=self.current_user,
            stats=stats,
            stats_json=json.dumps(stats, ensure_ascii=False),
        )


class ScreenDataApiHandler(AdminBaseHandler):
    def get(self):
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(_collect_stats()))


def _collect_stats():
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
        # Sentiment distribution
        sent_rows = conn.execute(
            """SELECT COALESCE(sentiment,'未分析') s, COUNT(*) c
               FROM watchtower_items GROUP BY s"""
        ).fetchall()
        # Hot words from watchtower titles
        titles = conn.execute(
            "SELECT title FROM watchtower_items ORDER BY id DESC LIMIT 200"
        ).fetchall()

    session_count = ChatRepository.count_all_sessions()

    msg_trend = [{"date": r["d"], "count": r["c"]} for r in trend_rows]
    sentiment_dist = [{"name": r["s"], "value": r["c"]} for r in sent_rows]

    # Simple word frequency for hot words
    import re

    word_freq: dict = {}
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
