import asyncio
import json
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from app.models.watchtower import SourceRepository as WatchtowerRepository

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class WatchtowerScraper:
    @staticmethod
    def parse_headers(raw_headers: str) -> dict:
        """解析raw格式请求头"""
        headers = {}
        for line in raw_headers.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()
        return headers

    @staticmethod
    def build_url(template: str, keyword: str, page: int) -> str:
        """构建请求URL"""
        page_offset = page * 10  # 百度新闻分页规则: pn=0,10,20...
        encoded_keyword = quote(keyword, safe="")
        return template.replace("{关键词}", encoded_keyword).replace(
            "{分页步进}", str(page_offset)
        )

    @staticmethod
    def _ensure_user_agent(headers: dict) -> dict:
        """确保请求头包含 User-Agent 和基本浏览器伪装头"""
        for key, val in DEFAULT_HEADERS.items():
            if key not in headers and key.lower() not in headers:
                headers[key] = val
        return headers

    @staticmethod
    def _scrape_baidu_news(soup: BeautifulSoup) -> list:
        """抓取百度新闻搜索结果"""
        items = []
        for div in soup.select(".result-op"):
            title_elem = div.select_one("h3 a")
            if not title_elem:
                continue

            snippet_elem = div.select_one(".c-font-normal")
            source_elem = div.select_one(".c-color-gray")
            time_elem = div.select_one(".c-color-gray2")

            items.append(
                {
                    "title": title_elem.get_text(strip=True),
                    "url": title_elem.get("href", ""),
                    "snippet": snippet_elem.get_text(strip=True)
                    if snippet_elem
                    else "",
                    "source": source_elem.get_text(strip=True)
                    if source_elem
                    else "百度新闻",
                    "published_time": time_elem.get_text(strip=True)
                    if time_elem
                    else "",
                }
            )

        return items

    @staticmethod
    def _scrape_bing_web(soup: BeautifulSoup) -> list:
        """抓取 Bing 网页搜索结果 — 多选择器回退"""
        items = []
        # Try multiple selector patterns Bing uses across regions/versions
        for li in soup.select(
            "#b_results > li.b_algo, #b_results .b_algo, "
            "ol#b_results > li.b_algo, "
            ".b_results li.b_algo, "
            "li.b_algo"
        ):
            title_elem = li.select_one("h2 a, h2 a[href], .b_title a")
            if not title_elem:
                continue

            snippet_elem = li.select_one(
                ".b_caption p, .b_lineclamp2, .b_algoSlug, .b_caption"
            )
            cite_elem = li.select_one("cite, .b_attribution")

            source_domain = ""
            if cite_elem:
                source_domain = cite_elem.get_text(strip=True)

            items.append(
                {
                    "title": title_elem.get_text(strip=True),
                    "url": title_elem.get("href", ""),
                    "snippet": snippet_elem.get_text(strip=True)
                    if snippet_elem
                    else "",
                    "source": source_domain or "Bing搜索",
                    "published_time": "",
                }
            )
        return items

    @staticmethod
    def _scrape_bing_news(soup: BeautifulSoup) -> list:
        """抓取 Bing 新闻搜索结果 — 多选择器回退"""
        items = []
        for card in soup.select(
            ".news-card, .newsitem, article.news-card, "
            "[data-newsitem], .bt_newsCard, "
            ".news-card-body, div.newsitem"
        ):
            title_elem = card.select_one(".title, a.title, h3 a, .news-title, a[href]")
            if not title_elem:
                continue

            snippet_elem = card.select_one(
                ".snippet, .news-snippet, .news-desc, .description, p, .body"
            )
            source_elem = card.select_one(
                ".source, .news-source, .provider, [data-author], .source-group"
            )
            time_elem = card.select_one("time, .time, .date, [datetime], .when, span")

            pub_time = ""
            if time_elem:
                pub_time = time_elem.get("datetime", "") or time_elem.get_text(
                    strip=True
                )

            items.append(
                {
                    "title": title_elem.get_text(strip=True),
                    "url": title_elem.get("href", ""),
                    "snippet": snippet_elem.get_text(strip=True)
                    if snippet_elem
                    else "",
                    "source": source_elem.get_text(strip=True)
                    if source_elem
                    else "Bing新闻",
                    "published_time": pub_time,
                }
            )
        return items

    @staticmethod
    def _scrape_duckduckgo(soup: BeautifulSoup) -> list:
        """抓取 DuckDuckGo HTML / Lite 搜索结果"""
        items = []
        for result in soup.select(
            ".result, .web-result, .result--web, article.result, "
            ".result__body, tr.result-sponsored, tr.result-snippet"
        ):
            title_elem = result.select_one(
                ".result__a, .result__title a, a.result__a, h2 a, a.result-link"
            )
            if not title_elem:
                continue

            snippet_elem = result.select_one(
                ".result__snippet, .result-snippet, .snippet, "
                "td.result-snippet, .result__extract"
            )
            url_elem = result.select_one(
                ".result__url, .result-link, .link-text, .result__extras__url"
            )

            items.append(
                {
                    "title": title_elem.get_text(strip=True),
                    "url": title_elem.get("href", ""),
                    "snippet": snippet_elem.get_text(strip=True)
                    if snippet_elem
                    else "",
                    "source": url_elem.get_text(strip=True)
                    if url_elem
                    else "DuckDuckGo",
                    "published_time": "",
                }
            )
        return items

    @staticmethod
    def _scrape_sogou_web(soup: BeautifulSoup) -> list:
        """抓取搜狗网页搜索结果"""
        items = []
        for result in soup.select(
            ".results .result, .rb, .vrwrap, .vrwrap, .result-item"
        ):
            title_elem = result.select_one(
                "h3 a, .vr-title a, .vrTitle a, .result-title a"
            )
            if not title_elem:
                continue

            snippet_elem = result.select_one(
                ".star-wiki, .space-txt, .result-desc, "
                ".str-text, .str_info_div, .abstract, p"
            )
            source_elem = result.select_one(
                ".result-source, cite, .source, .vr-header-site, .source-site"
            )
            date_elem = result.select_one(".result-date, .date, .time, .str-time")

            pub_time = ""
            if date_elem:
                pub_time = date_elem.get_text(strip=True)

            items.append(
                {
                    "title": title_elem.get_text(strip=True),
                    "url": title_elem.get("href", ""),
                    "snippet": snippet_elem.get_text(strip=True)
                    if snippet_elem
                    else "",
                    "source": source_elem.get_text(strip=True)
                    if source_elem
                    else "搜狗搜索",
                    "published_time": pub_time,
                }
            )
        return items

    @staticmethod
    def _scrape_rss(xml_content: bytes, config: dict) -> list:
        """解析 RSS 2.0 / Atom feed。

        config 可选字段:
          - item_tag: 自定义 item 标签名（默认自动检测 rss/channel/item 或 feed/entry）
          - title_tag, link_tag, desc_tag, date_tag: 自定义字段标签名
        """
        root = ET.fromstring(xml_content)
        items = []

        # 检测 feed 类型
        tag = root.tag.lower()
        is_atom = "atom" in tag or "feed" in tag

        # 自定义标签名，优先用 config 中的，其次用默认值
        if is_atom:
            ns_uri = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""

            entry_tag = config.get("item_tag") or "entry"
            title_tag = config.get("title_tag") or "title"
            link_tag = config.get("link_tag") or "link"
            desc_tag = config.get("desc_tag") or "summary"
            date_tag = config.get("date_tag") or "published"

            # 构建命名空间版本的标签名
            def _fmt(t: str) -> str:
                return f"{{{ns_uri}}}{t}" if ns_uri else t

            for entry in root.iter(_fmt(entry_tag) if ns_uri else entry_tag):
                title_elem = (
                    entry.find(_fmt(title_tag)) if ns_uri else entry.find(title_tag)
                )
                title = (
                    title_elem.text.strip()
                    if title_elem is not None and title_elem.text
                    else ""
                )

                link_elem = (
                    entry.find(_fmt(link_tag)) if ns_uri else entry.find(link_tag)
                )
                link = ""
                if link_elem is not None:
                    link = link_elem.get("href") or link_elem.text or ""
                    link = link.strip()

                desc_elem = (
                    entry.find(_fmt(desc_tag)) if ns_uri else entry.find(desc_tag)
                )
                desc = (desc_elem.text or "").strip() if desc_elem is not None else ""

                date_elem = (
                    entry.find(_fmt(date_tag)) if ns_uri else entry.find(date_tag)
                )
                pubdate = (
                    (date_elem.text or "").strip() if date_elem is not None else ""
                )

                items.append(
                    {
                        "title": title,
                        "url": link,
                        "snippet": desc[:500] if desc else "",
                        "source": "",
                        "published_time": pubdate,
                    }
                )
        else:
            # RSS 2.0
            item_tag = config.get("item_tag") or "item"
            title_tag = config.get("title_tag") or "title"
            link_tag = config.get("link_tag") or "link"
            desc_tag = config.get("desc_tag") or "description"
            date_tag = config.get("date_tag") or "pubDate"

            for item in root.iter(item_tag):
                title_elem = item.find(title_tag)
                title = (
                    title_elem.text.strip()
                    if title_elem is not None and title_elem.text
                    else ""
                )

                link_elem = item.find(link_tag)
                link = (link_elem.text or "").strip() if link_elem is not None else ""

                desc_elem = item.find(desc_tag)
                desc = (desc_elem.text or "").strip() if desc_elem is not None else ""

                date_elem = item.find(date_tag)
                pubdate = (
                    (date_elem.text or "").strip() if date_elem is not None else ""
                )

                items.append(
                    {
                        "title": title,
                        "url": link,
                        "snippet": desc[:500] if desc else "",
                        "source": "",
                        "published_time": pubdate,
                    }
                )

        return items

    @staticmethod
    def _resolve_json_path(data: dict | list, path: str) -> list:
        """按点号分隔的路径从 JSON 结构中提取列表。

        例如 path="data.items" → data["data"]["items"]
        空字符串表示 data 本身就是列表。
        """
        if not path:
            return data if isinstance(data, list) else []
        current = data
        for segment in path.split("."):
            if isinstance(current, dict):
                current = current.get(segment)
                if current is None:
                    return []
            elif isinstance(current, list):
                # 如果中间遇到列表，尝试对每个元素取子字段后展平
                result = []
                for elem in current:
                    if isinstance(elem, dict):
                        val = elem.get(segment)
                        if isinstance(val, list):
                            result.extend(val)
                        elif val is not None:
                            result.append(val)
                    elif isinstance(elem, list):
                        result.extend(elem)
                current = result
            else:
                return []
        return current if isinstance(current, list) else []

    @staticmethod
    def _scrape_api(json_data: dict | list, config: dict) -> list:
        """解析 JSON API 响应。

        config 字段:
          - data_path: JSON 路径，点号分隔（如 "data.items"）。空字符串表示根为列表。
          - title_field: 标题字段名（默认 "title"）
          - url_field: 链接字段名（默认 "url"）
          - content_field: 内容字段名（默认 "content"）
          - date_field: 日期字段名（默认 "published_at"）
          - source_field: 来源字段名（默认 "source"）
        """
        data_path = config.get("data_path", "")
        rows = WatchtowerScraper._resolve_json_path(json_data, data_path)

        title_field = config.get("title_field", "title")
        url_field = config.get("url_field", "url")
        content_field = config.get("content_field", "content")
        date_field = config.get("date_field", "published_at")
        source_field = config.get("source_field", "source")

        items = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            items.append(
                {
                    "title": str(row.get(title_field, "") or ""),
                    "url": str(row.get(url_field, "") or ""),
                    "snippet": str(row.get(content_field, "") or ""),
                    "source": str(row.get(source_field, "") or ""),
                    "published_time": str(row.get(date_field, "") or ""),
                }
            )
        return items

    @staticmethod
    def _scrape_generic(soup: BeautifulSoup, config: dict) -> list:
        """通用 HTML 链接提取。

        config 可选字段（均为 CSS 选择器）:
          - container_selector: 每条结果的容器元素（默认 "article, .post, .item, li"）
          - title_selector: 标题元素（默认 "h1 a, h2 a, h3 a, a.title"）
          - link_selector: 链接元素，与 title_selector 合并使用
          - snippet_selector: 摘要元素（默认 ".snippet, .desc, .description, p"）
          - date_selector: 日期元素（默认 "time, .date, .time, .pubdate"）
          - source_selector: 来源元素（默认 ".source, .author"）
        """
        container_sel = config.get("container_selector") or "article, .post, .item, li"
        title_sel = config.get("title_selector") or "h1 a, h2 a, h3 a, a.title"
        snippet_sel = (
            config.get("snippet_selector") or ".snippet, .desc, .description, p"
        )
        date_sel = config.get("date_selector") or "time, .date, .time, .pubdate"
        source_sel = config.get("source_selector") or ".source, .author"

        containers = soup.select(container_sel)
        if not containers:
            containers = [soup]

        items = []
        for container in containers:
            title_elem = container.select_one(title_sel)
            if not title_elem:
                continue

            link_elem = None
            if config.get("link_selector"):
                link_elem = container.select_one(config["link_selector"])
            if not link_elem:
                link_elem = (
                    title_elem if title_elem.name == "a" else title_elem.find("a")
                )

            link = ""
            if link_elem is not None:
                link = link_elem.get("href", "") or ""

            snippet_elem = container.select_one(snippet_sel)
            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

            source_elem = container.select_one(source_sel)
            source_name = source_elem.get_text(strip=True) if source_elem else ""

            date_elem = container.select_one(date_sel)
            pubdate = ""
            if date_elem:
                pubdate = date_elem.get("datetime", "") or date_elem.get_text(
                    strip=True
                )

            items.append(
                {
                    "title": title_elem.get_text(strip=True),
                    "url": link,
                    "snippet": snippet[:500] if snippet else "",
                    "source": source_name,
                    "published_time": pubdate,
                }
            )

        return items

    @staticmethod
    def scrape_page(
        url: str,
        headers: dict,
        source_type: str = "baidu_news",
        config_json: dict | None = None,
    ) -> list:
        """同步抓取单页（在线程池中执行）。

        根据 source_type 分发到不同的解析器：
          - "baidu_news": 百度新闻 CSS 选择器
          - "rss": RSS 2.0 / Atom feed 解析
          - "api": JSON API 响应解析
          - "generic": 通用 HTML 链接提取
        """
        headers = WatchtowerScraper._ensure_user_agent(headers)
        config = config_json or {}

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        if source_type == "rss":
            return WatchtowerScraper._scrape_rss(response.content, config)
        if source_type == "api":
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError):
                return []
            return WatchtowerScraper._scrape_api(data, config)
        if source_type == "bing_web":
            soup = BeautifulSoup(response.content, "html.parser")
            return WatchtowerScraper._scrape_bing_web(soup)
        if source_type == "bing_news":
            soup = BeautifulSoup(response.content, "html.parser")
            return WatchtowerScraper._scrape_bing_news(soup)
        if source_type == "duckduckgo":
            soup = BeautifulSoup(response.content, "html.parser")
            return WatchtowerScraper._scrape_duckduckgo(soup)
        if source_type == "sogou_web":
            soup = BeautifulSoup(response.content, "html.parser")
            return WatchtowerScraper._scrape_sogou_web(soup)
        if source_type == "generic":
            soup = BeautifulSoup(response.content, "html.parser")
            return WatchtowerScraper._scrape_generic(soup, config)
        # 默认: baidu_news
        soup = BeautifulSoup(response.content, "html.parser")
        return WatchtowerScraper._scrape_baidu_news(soup)

    @staticmethod
    async def scrape_source_async(
        source_id: int, keyword: str, pages: int, limit: int
    ) -> list:
        """异步抓取数据源（多页），按 source_type 分发解析策略。"""
        source = WatchtowerRepository.get_source(source_id)
        if not source:
            return []

        source_type = source["source_type"] or "baidu_news"
        raw_config = source["config_json"] or "{}"
        try:
            config_json: dict = (
                json.loads(raw_config) if isinstance(raw_config, str) else raw_config
            )
        except (json.JSONDecodeError, TypeError):
            config_json = {}

        headers = WatchtowerScraper.parse_headers(
            source["request_headers"] if source["request_headers"] else ""
        )

        # RSS 源没有分页，只请求一次；获取后按关键词过滤
        if source_type == "rss":
            from tornado.ioloop import IOLoop

            url = source["url"] or ""
            items = await IOLoop.current().run_in_executor(
                None,
                WatchtowerScraper.scrape_page,
                url,
                headers,
                source_type,
                config_json,
            )
            if keyword:
                kw_lower = keyword.lower()
                items = [
                    it
                    for it in items
                    if kw_lower in (it.get("title") or "").lower()
                    or kw_lower in (it.get("snippet") or "").lower()
                ]
            return items[:limit]

        all_items = []
        from tornado.ioloop import IOLoop

        for page in range(pages):
            url_template = (
                source["url_template"] if source["url_template"] else source["url"]
            )
            url = WatchtowerScraper.build_url(url_template, keyword, page)

            items = await IOLoop.current().run_in_executor(
                None,
                WatchtowerScraper.scrape_page,
                url,
                headers,
                source_type,
                config_json,
            )

            all_items.extend(items[:limit])

            if len(all_items) >= limit:
                break

            await asyncio.sleep(0.5)

        return all_items[:limit]
