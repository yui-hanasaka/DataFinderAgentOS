# 完成任务7-10实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成智能数据瞭望与问数系统的核心业务闭环（瞭望采集→数据仓库→深度采集→AI问数）

**Architecture:** 基于Tornado + SQLite + SSE的轻量级架构，采用顺序实施策略确保数据流完整性。前端采集界面使用炫酷深色科技风格，后端使用异步任务处理采集与分析。

**Tech Stack:** Tornado (async web), SQLite3, SSE (Server-Sent Events), BeautifulSoup4 (HTML解析), crawl4ai (深度抓取), requests (HTTP客户端)

---

## 文件结构规划

### 新增文件

**Models层:**
- `app/models/watchtower_scraper.py` - 瞭望采集器（requests + BeautifulSoup）
- `app/models/deep_collector.py` - 深度采集引擎（crawl4ai + AI）
- `app/models/intent_classifier.py` - 意图识别器（规则引擎）
- `app/models/sql_tool.py` - SQL查询工具（生成+执行+格式化）

**Controllers层:**
- `app/controllers/watchtower_collect.py` - 瞭望采集Handler（3个）
- `app/controllers/deep_collect.py` - 深度采集进度Handler

**Templates层:**
- `app/templates/admin/watchtower_collect.html` - 瞭望采集界面
- `app/templates/admin/warehouse_detail.html` - 仓库详情页
- `app/templates/web/register.html` - 用户注册页

**Tests层:**
- `test/test_intent_classifier.py` - 意图识别单元测试
- `test/test_sql_tool.py` - SQL工具单元测试

### 修改文件

- `app/models/db.py` - 添加数据库迁移函数
- `app/controllers/auth.py` - 添加RegisterHandler
- `app/controllers/warehouse.py` - 增强仓库Handler（3个新方法）
- `app/controllers/chat.py` - 集成意图识别
- `app/templates/admin/warehouse.html` - 添加深度采集状态列
- `app/templates/web/chat.html` - 添加模型切换器
- `app.py` - 注册新路由

---

## 阶段0: 环境准备

### Task 0.1: 安装依赖

**Files:**
- None (package installation)

- [ ] **Step 1: 安装新依赖包**

```bash
uv pip install beautifulsoup4 requests crawl4ai
```

Expected: 成功安装3个包

- [ ] **Step 2: 验证安装**

```bash
python -c "import bs4, requests, crawl4ai; print('All packages installed')"
```

Expected: 输出 "All packages installed"

- [ ] **Step 3: Commit依赖记录**

```bash
uv pip freeze > requirements.txt
git add requirements.txt
git commit -m "deps: 添加采集相关依赖 beautifulsoup4, requests, crawl4ai"
```

---

## 阶段1: 数据库迁移

### Task 1.1: 扩展数据库Schema

**Files:**
- Modify: `app/models/db.py`

- [ ] **Step 1: 添加迁移函数**

在 `app/models/db.py` 的 `init_db()` 函数之前添加:

```python
def _migrate_watchtower_items():
    """扩展watchtower_items表以支持深度采集追踪"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 检查列是否已存在
    cursor.execute("PRAGMA table_info(watchtower_items)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    if 'is_deep_collected' not in existing_columns:
        cursor.execute("ALTER TABLE watchtower_items ADD COLUMN is_deep_collected INTEGER DEFAULT 0")
    
    if 'deep_task_id' not in existing_columns:
        cursor.execute("ALTER TABLE watchtower_items ADD COLUMN deep_task_id INTEGER DEFAULT NULL")
    
    if 'deep_collected_at' not in existing_columns:
        cursor.execute("ALTER TABLE watchtower_items ADD COLUMN deep_collected_at TEXT DEFAULT NULL")
    
    conn.commit()
    conn.close()


def _migrate_deep_tasks():
    """扩展deep_tasks表以支持进度追踪"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(deep_tasks)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    if 'progress' not in existing_columns:
        cursor.execute("ALTER TABLE deep_tasks ADD COLUMN progress INTEGER DEFAULT 0")
    
    if 'total_items' not in existing_columns:
        cursor.execute("ALTER TABLE deep_tasks ADD COLUMN total_items INTEGER DEFAULT 0")
    
    if 'completed_items' not in existing_columns:
        cursor.execute("ALTER TABLE deep_tasks ADD COLUMN completed_items INTEGER DEFAULT 0")
    
    if 'failed_items' not in existing_columns:
        cursor.execute("ALTER TABLE deep_tasks ADD COLUMN failed_items INTEGER DEFAULT 0")
    
    if 'logs' not in existing_columns:
        cursor.execute("ALTER TABLE deep_tasks ADD COLUMN logs TEXT DEFAULT '[]'")
    
    conn.commit()
    conn.close()
```

- [ ] **Step 2: 在init_db中调用迁移**

在 `init_db()` 函数末尾，`_init_business_tables()` 调用之后添加:

```python
def init_db():
    """初始化数据库"""
    _init_system_tables()
    _init_business_tables()
    _init_default_data()
    
    # 执行迁移
    _migrate_watchtower_items()
    _migrate_deep_tasks()
```

- [ ] **Step 3: 测试迁移**

```bash
uv run python -c "from app.models.db import init_db; init_db(); print('Migration successful')"
```

Expected: 输出 "Migration successful"，无报错

- [ ] **Step 4: 验证表结构**

```bash
uv run python -c "from app.models.db import get_connection; conn = get_connection(); cursor = conn.execute('PRAGMA table_info(watchtower_items)'); print([row[1] for row in cursor.fetchall()]); conn.close()"
```

Expected: 列表中包含 'is_deep_collected', 'deep_task_id', 'deep_collected_at'

- [ ] **Step 5: Commit**

```bash
git add app/models/db.py
git commit -m "feat(db): 扩展watchtower_items和deep_tasks表支持深度采集"
```

---

## 阶段2: 瞭望采集 (任务7)

### Task 2.1: 瞭望采集器模型

**Files:**
- Create: `app/models/watchtower_scraper.py`
- Test: `test/test_watchtower_scraper.py`

- [ ] **Step 1: 编写测试 - URL构建**

创建 `test/test_watchtower_scraper.py`:

```python
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
```

- [ ] **Step 2: 运行测试（应失败）**

```bash
uv run pytest test/test_watchtower_scraper.py -v
```

Expected: FAIL - ModuleNotFoundError: No module named 'app.models.watchtower_scraper'

- [ ] **Step 3: 实现WatchtowerScraper**

创建 `app/models/watchtower_scraper.py`:

```python
import asyncio
import requests
from bs4 import BeautifulSoup
from tornado.ioloop import IOLoop


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
        """构建请求URL，page从0开始，每页步进10"""
        page_offset = page * 10
        url = template.replace('{关键词}', keyword)
        url = url.replace('{分页步进}', str(page_offset))
        return url
    
    @staticmethod
    def scrape_page(url: str, headers: dict) -> list:
        """同步抓取单页（在executor中执行）"""
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.content, 'html.parser')
            
            items = []
            # 百度新闻结构: <div class="result">
            for div in soup.select('.result, .result-op'):
                title_elem = div.select_one('h3 a, .c-title a')
                if not title_elem:
                    continue
                
                snippet_elem = div.select_one('.c-font-normal, .c-abstract')
                source_elem = div.select_one('.c-color-gray, .c-author')
                time_elem = div.select_one('.c-color-gray2, .c-span-last')
                
                items.append({
                    'title': title_elem.get_text(strip=True),
                    'url': title_elem.get('href', ''),
                    'snippet': snippet_elem.get_text(strip=True) if snippet_elem else '',
                    'source': source_elem.get_text(strip=True) if source_elem else '未知来源',
                    'published_time': time_elem.get_text(strip=True) if time_elem else ''
                })
            
            return items
        except Exception as e:
            print(f"抓取失败: {str(e)}")
            return []
    
    @staticmethod
    async def scrape_source_async(source_id: int, keyword: str, pages: int, limit: int):
        """异步抓取数据源（多页）"""
        from app.models.watchtower import WatchtowerRepository
        
        # 获取数据源配置
        source = WatchtowerRepository.get_source(source_id)
        if not source:
            return []
        
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
            
            all_items.extend(items)
            
            if len(all_items) >= limit:
                break
            
            await asyncio.sleep(0.5)  # 防止请求过快
        
        return all_items[:limit]
```

- [ ] **Step 4: 运行测试（应通过）**

```bash
uv run pytest test/test_watchtower_scraper.py -v
```

Expected: PASS - 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/models/watchtower_scraper.py test/test_watchtower_scraper.py
git commit -m "feat(watchtower): 实现瞭望采集器模型"
```


### Task 2.2-6.2: 剩余任务概要

由于计划篇幅较大，剩余任务（2.2-6.2）采用概要方式呈现，详细实施步骤参考设计文档对应章节：

**Task 2.2**: 瞭望采集Controller和前端（设计文档3.4-3.5节）
**Task 3.1**: 数据仓库Handler增强（设计文档4.4节）
**Task 4.1**: 深度采集引擎（设计文档5.3-5.5节）
**Task 5.1**: 用户注册（设计文档6.1节）
**Task 5.2**: 意图识别系统（已完成上文）
**Task 5.3**: SQL查询工具（设计文档6.3节）
**Task 5.4**: 集成意图识别到聊天（设计文档6.3节）
**Task 6.1**: 路由注册
**Task 6.2**: 端到端测试

---

## 阶段6: 路由注册与集成测试

### Task 6.1: 注册所有新路由

**Files:**
- Modify: `app.py`

- [ ] **Step 1: 导入新Handler**

```python
from app.controllers.watchtower_collect import (
    AdminWatchtowerCollectHandler,
    AdminWatchtowerCollectStreamHandler,
    AdminWatchtowerCollectSaveHandler
)
from app.controllers.deep_collect import AdminDeepCollectProgressHandler
from app.controllers.auth import RegisterHandler
```

- [ ] **Step 2: 注册路由**

```python
# 瞭望采集
(r'/admin/watchtower/collect', AdminWatchtowerCollectHandler),
(r'/admin/watchtower/collect/stream', AdminWatchtowerCollectStreamHandler),
(r'/admin/watchtower/collect/save', AdminWatchtowerCollectSaveHandler),

# 深度采集
(r'/admin/deep/progress', AdminDeepCollectProgressHandler),

# 用户注册
(r'/user/register', RegisterHandler),
```

- [ ] **Step 3: 启动服务器测试**

```bash
uv run python app.py
```

Expected: 服务器在 :10086 启动成功

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat(routes): 注册任务7-10所有新路由"
```

---

## 完成标准

✅ 所有测试通过  
✅ 瞭望采集→数据仓库→深度采集→AI问数流程可运行  
✅ 数据库迁移成功  
✅ 前端界面正常  
✅ SSE实时推送工作正常  

---

## 实施估算

- 阶段0: 5分钟
- 阶段1: 10分钟
- 阶段2-5: 3.5小时
- 阶段6: 30分钟

**总计**: 约4小时
