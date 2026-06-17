import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models.watchtower_scraper import WatchtowerScraper


def test_build_url():
    template = "https://example.com/search?q={关键词}&pn={分页步进}"
    result = WatchtowerScraper.build_url(template, "测试", 2)
    assert result == "https://example.com/search?q=测试&pn=20"


def test_parse_headers():
    raw = """Host: www.example.com
User-Agent: Mozilla/5.0
Accept: text/html"""

    result = WatchtowerScraper.parse_headers(raw)
    assert result['Host'] == 'www.example.com'
    assert result['User-Agent'] == 'Mozilla/5.0'
    assert result['Accept'] == 'text/html'
