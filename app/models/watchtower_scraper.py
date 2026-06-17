import asyncio
import requests
from bs4 import BeautifulSoup
from tornado.ioloop import IOLoop

from app.models.watchtower import SourceRepository as WatchtowerRepository


class WatchtowerScraper:
    @staticmethod
    def parse_headers(raw_headers: str) -> dict:
        """解析raw格式请求头"""
        headers = {}
        for line in raw_headers.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip()] = value.strip()
        return headers

    @staticmethod
    def build_url(template: str, keyword: str, page: int) -> str:
        """构建请求URL"""
        page_offset = page * 10  # 百度新闻分页规则: pn=0,10,20...
        return template.replace('{关键词}', keyword).replace('{分页步进}', str(page_offset))

    @staticmethod
    def scrape_page(url: str, headers: dict) -> list:
        """同步抓取单页（在executor中执行）"""
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')

        items = []
        # 百度新闻结构: <div class="result-op">
        for div in soup.select('.result-op'):
            title_elem = div.select_one('h3 a')
            if not title_elem:
                continue

            snippet_elem = div.select_one('.c-font-normal')
            source_elem = div.select_one('.c-color-gray')
            time_elem = div.select_one('.c-color-gray2')

            items.append({
                'title': title_elem.get_text(strip=True),
                'url': title_elem.get('href', ''),
                'snippet': snippet_elem.get_text(strip=True) if snippet_elem else '',
                'source': source_elem.get_text(strip=True) if source_elem else '百度新闻',
                'published_time': time_elem.get_text(strip=True) if time_elem else ''
            })

        return items

    @staticmethod
    async def scrape_source_async(source_id: int, keyword: str, pages: int, limit: int):
        """异步抓取数据源（多页）"""
        # 获取数据源配置
        source = WatchtowerRepository.get_source(source_id)
        headers = WatchtowerScraper.parse_headers(source['request_headers'])

        all_items = []
        for page in range(pages):
            url = WatchtowerScraper.build_url(source['url_template'], keyword, page)

            # 在线程池中执行阻塞操作
            items = await IOLoop.current().run_in_executor(
                None,
                WatchtowerScraper.scrape_page,
                url,
                headers
            )

            all_items.extend(items[:limit])  # 限制数量

            if len(all_items) >= limit:
                break

            await asyncio.sleep(0.5)  # 防止请求过快

        return all_items[:limit]
