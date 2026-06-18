from app.models.watchtower_scraper import WatchtowerScraper


def test_build_url() -> None:
    template = "https://example.com/search?q={关键词}&pn={分页步进}"
    result = WatchtowerScraper.build_url(template, "测试", 2)
    assert result == "https://example.com/search?q=%E6%B5%8B%E8%AF%95&pn=20"


def test_parse_headers() -> None:
    raw = """Host: www.example.com
User-Agent: Mozilla/5.0
Accept: text/html"""

    result = WatchtowerScraper.parse_headers(raw)
    assert result["Host"] == "www.example.com"
    assert result["User-Agent"] == "Mozilla/5.0"
    assert result["Accept"] == "text/html"


def test_build_url_page_zero() -> None:
    template = "https://example.com/search?q={关键词}&pn={分页步进}"
    result = WatchtowerScraper.build_url(template, "test", 0)
    assert result == "https://example.com/search?q=test&pn=0"
