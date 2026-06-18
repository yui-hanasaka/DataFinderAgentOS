# Agentic架构增强 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现混合式轻量Agent架构——引入TaskAgent（显式前缀触发）、动态并发执行器、数字员工技能映射、瞭望采集多层selector回退、数据库迁移工具

**Architecture:** 在现有agent_loop之上新增TaskAgent重型模式，通过`/task`前缀显式触发。调度层(intent_router + employee技能映射)决定路由；执行层(TaskAgent + ConcurrentExecutor)处理复杂多步任务；工具层(watchtower_scraper增强)提供可靠采集能力；数据库层(db_migration + db_switcher增强)实现渐进式SQLite→MySQL迁移

**Tech Stack:** Python 3.12+, Tornado, SQLite3, crawl4ai, BeautifulSoup4, pymysql, psutil

**并行策略:** 第1轮(模块1+3+5独立开发) → 第2轮(模块2+4) → 第3轮(模块6集成测试)

---

### Task 1: 修复数据库初始化路径问题

**Files:**
- Modify: `app/models/db.py:19-21`

这是所有模块的前置条件——数据库文件路径必须正确。

- [ ] **Step 1: 修复DB_PATH默认路径**

```python
# app/models/db.py line 19-21 替换为:
DB_PATH = os.environ.get(
    "DATAFINDER_DB_PATH",
    os.path.join(_project_root(), "database", "app.db"),
)
```

- [ ] **Step 2: 确保init_db()创建目录**

```python
# app/models/db.py init_db() 函数开头添加:
def init_db() -> None:
    """Bootstrap database: create SQLite tables, seed data, then check..."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    # ... 后续现有逻辑保持不变 ...
```

- [ ] **Step 3: 启动服务器验证**

Run: `uv run python app.py`
Expected: Server starts without errors, `database/app.db` file created with all tables

- [ ] **Step 4: Commit**

```bash
git add app/models/db.py
git commit -m "fix: correct default DB_PATH to database/app.db and ensure directory exists"
```

---

## 轮次1：模块1 + 3 + 5（互不依赖，可并行开发）

---

### Task 2: 新增意图路由模块

**Files:**
- Create: `app/models/intent_router.py`

- [ ] **Step 1: 创建intent_router.py**

```python
"""Intent routing: decide direct agent_loop vs TaskAgent mode."""

from app.models.employee import EmployeeRepository

TASK_TRIGGERS: dict[str, dict] = {
    "/task": {"max_iterations": 8, "enable_reflection": True},
    "/深度分析": {"max_iterations": 6, "enable_reflection": True},
    "/批量处理": {"max_iterations": 10, "enable_reflection": False},
}


def route_message(user_text: str, employee_id: int | None) -> dict:
    """
    Returns:
        {"mode": "direct" | "task_agent", "cleaned_text": str, "task_config": dict}
    """
    for prefix, config in TASK_TRIGGERS.items():
        if user_text.startswith(prefix):
            cleaned = user_text[len(prefix):].strip()
            return {
                "mode": "task_agent",
                "cleaned_text": cleaned or user_text,
                "task_config": dict(config),
            }

    if employee_id:
        emp = EmployeeRepository.get_employee_with_tools(employee_id)
        if emp and emp.get("force_task_agent"):
            return {
                "mode": "task_agent",
                "cleaned_text": user_text,
                "task_config": emp.get("task_config") or {"max_iterations": 8},
            }

    return {"mode": "direct", "cleaned_text": user_text, "task_config": {}}
```

- [ ] **Step 2: 检查语法和类型**

Run: `uv run pyright app/models/intent_router.py`
Expected: 0 errors, 0 warnings

- [ ] **Step 3: Commit**

```bash
git add app/models/intent_router.py
git commit -m "feat: add intent router for /task prefix detection"
```

---

### Task 3: 增强EmployeeRepository——技能映射为工具列表

**Files:**
- Modify: `app/models/employee.py`

- [ ] **Step 1: 读取当前employee.py确认结构**

Run: `uv run python -c "from app.models.employee import EmployeeRepository; print(dir(EmployeeRepository))"`
Expected: List of existing methods

- [ ] **Step 2: 新增get_employee_with_tools()方法**

在 `EmployeeRepository` 类中添加以下静态方法：

```python
# app/models/employee.py — 在 EmployeeRepository 类中添加:

    _SKILL_TO_TOOL: dict[str, str] = {
        "web_search": "web_search",
        "code_exec": "code_execute",
        "watchtower": "watchtower_search",
        "warehouse": "warehouse_query",
        "deep_crawl": "deep_collect",
        "env_check": "env_info",
    }

    @staticmethod
    def get_employee_with_tools(employee_id: int) -> dict | None:
        """Return employee with allowed_tools derived from skills."""
        from app.models.db import get_connection
        import json

        emp_row = EmployeeRepository.get_employee(employee_id)
        if not emp_row:
            return None

        skills_raw = emp_row["skills"] or "[]"
        try:
            skills_data = json.loads(skills_raw)
        except (json.JSONDecodeError, TypeError):
            skills_data = []

        if isinstance(skills_data, list):
            # Legacy format: just skill IDs
            skill_ids = skills_data
            force_task_agent = False
            task_config = {}
        elif isinstance(skills_data, dict):
            # New format: {"skill_ids": [...], "force_task_agent": bool, "task_config": {...}}
            skill_ids = skills_data.get("skill_ids", [])
            force_task_agent = skills_data.get("force_task_agent", False)
            task_config = skills_data.get("task_config", {})
        else:
            skill_ids = []
            force_task_agent = False
            task_config = {}

        allowed_tools: list[str] = []
        if skill_ids:
            with get_connection() as conn:
                placeholders = ",".join(["?"] * len(skill_ids))
                rows = conn.execute(
                    f"SELECT code FROM skills WHERE id IN ({placeholders}) AND status='enabled'",
                    skill_ids,
                ).fetchall()
                for row in rows:
                    tool_name = EmployeeRepository._SKILL_TO_TOOL.get(row["code"])
                    if tool_name and tool_name not in allowed_tools:
                        allowed_tools.append(tool_name)

        result = dict(emp_row)
        result["allowed_tools"] = allowed_tools if allowed_tools else None
        result["force_task_agent"] = force_task_agent
        result["task_config"] = task_config
        return result
```

- [ ] **Step 3: 检查类型**

Run: `uv run pyright app/models/employee.py`
Expected: 0 errors, 0 warnings

- [ ] **Step 4: Commit**

```bash
git add app/models/employee.py
git commit -m "feat: add get_employee_with_tools() for skill-to-tool mapping"
```

---

### Task 4: 增强agent_loop——接收allowed_tools参数并过滤工具调用

**Files:**
- Modify: `app/agents/agent_loop.py`

- [ ] **Step 1: 修改run()签名和工具过滤逻辑**

在 `app/agents/agent_loop.py` 的 `run()` 函数中添加 `allowed_tools` 参数：

```python
# 修改 run() 签名:
async def run(
    user_text: str,
    messages: list[dict[str, Any]],
    model_row: dict[str, Any],
    stream_cb: StreamCallback,
    allowed_tools: list[str] | None = None,
) -> str:
```

在 `_stream_chat_once` 调用之前，按 `allowed_tools` 过滤 `TOOLS`：

```python
# 在 run() 函数中，_stream_chat_once 调用之前添加:
    # Filter tools based on employee's allowed_tools
    active_tools = TOOLS
    if allowed_tools is not None:
        active_tools = [t for t in TOOLS if t["function"]["name"] in allowed_tools]
```

然后在 `_stream_chat_once` 调用中传入 `active_tools`：

```python
# 修改 _stream_chat_once 调用:
                full_content, calls, usage = await _stream_chat_once(
                    api_key, messages, model_row, stream_cb
                )
```
修改为传入 `tools` 参数。需要同时修改 `_stream_chat_once` 以接收 `tools`：

```python
async def _stream_chat_once(
    api_key: str,
    messages: list[dict[str, Any]],
    model_row: dict[str, Any],
    stream_cb: StreamCallback,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
    # ... 内部把 tools=TOOLS 改为 tools=(tools or TOOLS):
    resp = await chat_complete(
        str(model_row["base_url"]),
        api_key,
        str(model_row["model_id"]),
        messages,
        temperature=float(model_row.get("temperature") or 0.7),
        max_tokens=int(model_row.get("max_tokens") or 1024),
        stream=True,
        tools=tools or TOOLS,
    )
```

- [ ] **Step 2: 检查类型**

Run: `uv run pyright app/agents/agent_loop.py`
Expected: 0 errors, 0 warnings

- [ ] **Step 3: Commit**

```bash
git add app/agents/agent_loop.py
git commit -m "feat: add allowed_tools filtering to agent_loop.run()"
```

---

### Task 5: 修改ChatSendHandler——集成意图路由和技能映射

**Files:**
- Modify: `app/controllers/chat.py:234-419`

- [ ] **Step 1: 在ChatSendHandler.post中添加路由逻辑**

在 `app/controllers/chat.py` 顶部添加导入：
```python
from app.models.intent_router import route_message
```

在 `ChatSendHandler.post()` 中，获得 `employee` 对象后（约第311行），添加路由：

```python
        # 在 employee 获取之后（第311行之后），messages 构建之前插入:
        # Route: decide direct agent_loop vs TaskAgent
        employee_with_tools = None
        allowed_tools: list[str] | None = None
        if employee:
            employee_with_tools = EmployeeRepository.get_employee_with_tools(
                session["employee_id"]
            )
            if employee_with_tools:
                allowed_tools = employee_with_tools.get("allowed_tools")

        route_result = route_message(user_text, session.get("employee_id"))
```

在调用 `agent_loop.run()` 处（第399行），传入 `allowed_tools`：

```python
            await agent_loop.run(
                user_text, messages, model_row, _sse, allowed_tools=allowed_tools
            )
```

- [ ] **Step 2: 为TaskAgent路由添加占位逻辑**

当 `route_result["mode"] == "task_agent"` 时，当前暂回退到 `agent_loop`（TaskAgent将在模块2实现）：

```python
        if route_result["mode"] == "task_agent":
            # TODO: 模块2完成后替换为 TaskAgent.run()
            # 当前回退：使用 agent_loop 但标注为task模式
            _ = route_result  # unused until TaskAgent is ready
```

- [ ] **Step 3: 运行现存测试确保无回归**

Run: `uv run pytest test/ -v`
Expected: All existing tests pass

- [ ] **Step 4: 检查并格式化**

```bash
uv run ruff check app/controllers/chat.py
uv run ruff format app/controllers/chat.py
uv run pyright
```

- [ ] **Step 5: Commit**

```bash
git add app/controllers/chat.py
git commit -m "feat: integrate intent_router and skill-to-tool mapping into ChatSendHandler"
```

---

### Task 6: 重构watchtower_scraper——_extract_item_from_container通用提取器

**Files:**
- Modify: `app/models/watchtower_scraper.py`

- [ ] **Step 1: 新增通用提取器方法**

在 `WatchtowerScraper` 类中添加：

```python
    @staticmethod
    def _extract_item_from_container(
        container: "BeautifulSoup",
        title_selectors: list[str],
        snippet_selectors: list[str],
        source_selectors: list[str],
        time_selectors: list[str],
    ) -> dict | None:
        """Extract an item from a container element with multi-selector fallback."""
        # Title extraction
        title_elem = None
        title_text = ""
        url = ""
        for selector in title_selectors:
            title_elem = container.select_one(selector)
            if title_elem:
                title_text = title_elem.get_text(strip=True)
                url = title_elem.get("href", "")
                if title_text and url:
                    break

        if not title_text:
            return None

        # Snippet extraction
        snippet = ""
        for selector in snippet_selectors:
            elem = container.select_one(selector)
            if elem:
                snippet = elem.get_text(strip=True)
                if snippet:
                    break

        # Source extraction
        source = ""
        for selector in source_selectors:
            elem = container.select_one(selector)
            if elem:
                source = elem.get_text(strip=True)
                if source:
                    break

        # Time extraction
        published_time = ""
        for selector in time_selectors:
            elem = container.select_one(selector)
            if elem:
                published_time = elem.get("datetime", "") or elem.get_text(strip=True)
                if published_time:
                    break

        return {
            "title": title_text[:200],
            "url": url,
            "snippet": snippet[:500],
            "source": source or "未知来源",
            "published_time": published_time,
        }
```

- [ ] **Step 2: 提交**

```bash
git add app/models/watchtower_scraper.py
git commit -m "feat: add _extract_item_from_container with multi-selector fallback"
```

---

### Task 7: 增强百度新闻采集——3层selector回退

**Files:**
- Modify: `app/models/watchtower_scraper.py` — `_scrape_baidu_news` 方法

- [ ] **Step 1: 重写_scrape_baidu_news添加回退层**

替换现有 `_scrape_baidu_news` 方法：

```python
    @staticmethod
    def _scrape_baidu_news(soup: "BeautifulSoup") -> list:
        """抓取百度新闻 — 3层selector回退"""
        items = []

        # Layer 1: standard selectors for current Baidu layout
        for div in soup.select(".result-op, .c-container"):
            item = WatchtowerScraper._extract_item_from_container(
                div,
                title_selectors=["h3 a", ".t a", "a.c-title"],
                snippet_selectors=[".c-font-normal", ".c-abstract", ".c-span9"],
                source_selectors=[".c-color-gray", ".c-author", ".source"],
                time_selectors=[".c-color-gray2", ".c-time", "time"],
            )
            if item:
                items.append(item)

        # Layer 2: semantic fallback
        if not items:
            for article in soup.select(
                "article, .news-item, .result, div[class*='result'], div[class*='news']"
            ):
                item = WatchtowerScraper._extract_item_from_container(
                    article,
                    title_selectors=["h1 a", "h2 a", "h3 a", "a[href]"],
                    snippet_selectors=["p", ".desc", ".summary", ".content"],
                    source_selectors=[".source", ".author", "cite", ".domain"],
                    time_selectors=["time", ".date", ".time", ".pubdate"],
                )
                if item:
                    items.append(item)

        # Layer 3: full-page link extraction
        if not items:
            items = WatchtowerScraper._fallback_extract_all_links(soup)

        return items
```

- [ ] **Step 2: 新增_baidu_news_fallback_all_links**

```python
    @staticmethod
    def _fallback_extract_all_links(soup: "BeautifulSoup") -> list:
        """Last resort: extract all valid links from page."""
        items = []
        for a in soup.select("a[href]"):
            title = a.get_text(strip=True)
            url = a.get("href", "")
            if len(title) < 10 or not url.startswith("http"):
                continue
            if len(items) >= 50:
                break
            items.append({
                "title": title[:200],
                "url": url,
                "snippet": "",
                "source": "通用提取",
                "published_time": "",
            })
        return items
```

- [ ] **Step 3: 以同样方式增强_scrape_bing_web和_scrape_generic**

复用 `_extract_item_from_container` 重构 `_scrape_bing_web` 和 `_scrape_generic`：

```python
    @staticmethod
    def _scrape_bing_web(soup: "BeautifulSoup") -> list:
        items = []
        for li in soup.select("li.b_algo, .b_algo, li[class*='result']"):
            item = WatchtowerScraper._extract_item_from_container(
                li,
                title_selectors=["h2 a", "a[href]"],
                snippet_selectors=[".b_caption p", ".b_lineclamp2", ".b_algoSlug", "p"],
                source_selectors=["cite", ".b_attribution"],
                time_selectors=["time", ".news_dt"],
            )
            if item:
                items.append(item)
        if not items:
            items = WatchtowerScraper._fallback_extract_all_links(soup)
        return items

    @staticmethod
    def _scrape_generic(soup: "BeautifulSoup", config: dict) -> list:
        container_sel = config.get("container_selector") or "article, .post, .item, li"
        title_sel = (config.get("title_selector") or "h1 a, h2 a, h3 a, a.title").split(", ")
        snippet_sel = (config.get("snippet_selector") or ".snippet, .desc, p").split(", ")
        date_sel = (config.get("date_selector") or "time, .date, .pubdate").split(", ")
        source_sel = (config.get("source_selector") or ".source, .author").split(", ")

        containers = soup.select(container_sel) or [soup]
        items = []
        for container in containers:
            item = WatchtowerScraper._extract_item_from_container(
                container,
                title_selectors=[s.strip() for s in title_sel],
                snippet_selectors=[s.strip() for s in snippet_sel],
                source_selectors=[s.strip() for s in source_sel],
                time_selectors=[s.strip() for s in date_sel],
            )
            if item:
                items.append(item)
        if not items:
            items = WatchtowerScraper._fallback_extract_all_links(soup)
        return items
```

- [ ] **Step 4: 检查类型和格式**

```bash
uv run ruff check app/models/watchtower_scraper.py
uv run ruff format app/models/watchtower_scraper.py
uv run pyright app/models/watchtower_scraper.py
```

- [ ] **Step 5: 运行现有测试**

Run: `uv run pytest test/test_watchtower_scraper.py -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add app/models/watchtower_scraper.py
git commit -m "feat: add 3-layer selector fallback for baidu_news, bing_web, generic scrapers"
```

---

### Task 8: 增强反爬策略——随机UA池和指数退避重试

**Files:**
- Modify: `app/models/watchtower_scraper.py` — `_ensure_user_agent` 和 `scrape_source_async`

- [ ] **Step 1: 增强_ensure_user_agent添加完整浏览器指纹**

替换现有 `_ensure_user_agent` 方法：

```python
    import random as _random

    _UA_POOL: list[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    @staticmethod
    def _ensure_user_agent(headers: dict) -> dict:
        if "User-Agent" not in headers and "user-agent" not in headers:
            headers["User-Agent"] = WatchtowerScraper._random.choice(
                WatchtowerScraper._UA_POOL
            )
        if "Accept" not in headers and "accept" not in headers:
            headers["Accept"] = (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/webp,*/*;q=0.8"
            )
        if "Accept-Language" not in headers and "accept-language" not in headers:
            headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
        if "Accept-Encoding" not in headers and "accept-encoding" not in headers:
            headers["Accept-Encoding"] = "gzip, deflate, br"
        if "DNT" not in headers and "dnt" not in headers:
            headers["DNT"] = "1"
        if "Connection" not in headers and "connection" not in headers:
            headers["Connection"] = "keep-alive"
        if "Upgrade-Insecure-Requests" not in headers:
            headers["Upgrade-Insecure-Requests"] = "1"
        return headers
```

- [ ] **Step 2: 给scrape_source_async添加3次指数退避重试**

在 `scrape_source_async` 方法中，将现有的单次 `scrape_page` 调用改为带重试循环：

```python
    import asyncio as _asyncio

    # 在 scrape_source_async 的 page 循环内部，替换单个 scrape_page 调用:
            for attempt in range(3):
                try:
                    items = await IOLoop.current().run_in_executor(
                        None,
                        WatchtowerScraper.scrape_page,
                        url,
                        headers,
                        source_type,
                        config_json,
                    )
                    if items:
                        all_items.extend(items[:limit])
                        break  # 成功
                    elif attempt < 2:
                        # 无结果但未报错，可能selector不匹配
                        await _asyncio.sleep(1.0 * (attempt + 1))
                except Exception as e:
                    from app.models.errors import log_error
                    log_error(
                        f"采集源{source_id} p{page+1} 重试{attempt+1}/3",
                        e,
                    )
                    if attempt < 2:
                        await _asyncio.sleep(2.0 * (attempt + 1))
```

- [ ] **Step 3: 检查**

```bash
uv run ruff check app/models/watchtower_scraper.py
uv run pyright app/models/watchtower_scraper.py
```

- [ ] **Step 4: Commit**

```bash
git add app/models/watchtower_scraper.py
git commit -m "feat: add UA rotation, browser fingerprint, and exponential backoff retry"
```

---

### Task 9: 新增采集日志表——watchtower_logs

**Files:**
- Modify: `app/models/db.py` — 添加新表
- Modify: `app/models/watchtower_scraper.py` — 添加日志记录调用

- [ ] **Step 1: 在db.py中添加watchtower_logs表**

在 `app/models/db.py` 的 `_init_business_tables` 或初始化逻辑中添加：

```python
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchtower_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            keyword TEXT,
            url TEXT,
            status TEXT NOT NULL DEFAULT 'unknown',
            items_count INTEGER DEFAULT 0,
            error_message TEXT,
            response_time INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(source_id) REFERENCES watchtower_sources(id) ON DELETE CASCADE
        )
    """)
```

- [ ] **Step 2: 在watchtower_scraper中添加日志记录函数**

```python
# app/models/watchtower_scraper.py 模块级函数:
def _log_scrape_result(
    source_id: int,
    url: str,
    status: str,
    items_count: int,
    error: str | None,
    response_time: int,
) -> None:
    """Record scrape result to watchtower_logs."""
    try:
        from app.models.db import get_connection
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO watchtower_logs(source_id, url, status, items_count,"
                " error_message, response_time) VALUES(?,?,?,?,?,?)",
                (source_id, url, status, items_count, error, response_time),
            )
    except Exception:
        pass  # Logging failure must not break scraping
```

- [ ] **Step 3: 在scrape_page中调用日志记录**

在 `scrape_page` 方法中添加计时和日志：

```python
    @staticmethod
    def scrape_page(url, headers, source_type="baidu_news", config_json=None):
        import time
        start_time = time.time()
        headers = WatchtowerScraper._ensure_user_agent(headers)
        config = config_json or {}
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            # ... 现有解析逻辑 ...
            items = ...  # 提取到的条目
            rt = int((time.time() - start_time) * 1000)
            # Log success (best-effort)
            _log_scrape_result(
                0, url, "success" if items else "partial",
                len(items), None, rt
            )
            return items
        except Exception as e:
            rt = int((time.time() - start_time) * 1000)
            _log_scrape_result(0, url, "failed", 0, str(e), rt)
            raise
```

- [ ] **Step 4: 启动服务器验证表创建**

Run: `uv run python app.py`
Expected: `watchtower_logs` table created without errors

- [ ] **Step 5: Commit**

```bash
git add app/models/db.py app/models/watchtower_scraper.py
git commit -m "feat: add watchtower_logs table and scrape result logging"
```

---

### Task 10: 数据库迁移工具——结构导出

**Files:**
- Create: `app/models/db_migration.py`

- [ ] **Step 1: 创建db_migration.py**

```python
"""Database migration: SQLite → MySQL schema export and data transfer."""

from app.models.db import _sqlite_raw_connect
from app.models.db_ddl import to_mysql_ddl


class DatabaseMigrator:
    """Export SQLite schema as MySQL DDL and migrate data in batches."""

    @staticmethod
    def export_schema_to_mysql() -> list[str]:
        """Export all SQLite tables as MySQL CREATE TABLE statements."""
        ddl_list: list[str] = []
        with _sqlite_raw_connect() as conn:
            tables = conn.execute(
                "SELECT name, sql FROM sqlite_master"
                " WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
                " ORDER BY name"
            ).fetchall()
            for row in tables:
                mysql_ddl = to_mysql_ddl(row["sql"])
                mysql_ddl = (
                    mysql_ddl.rstrip(";").rstrip(")")
                    + ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
                )
                ddl_list.append(mysql_ddl)
        return ddl_list
```

- [ ] **Step 2: 测试导出**

Run: `uv run python -c "from app.models.db_migration import DatabaseMigrator; ddls = DatabaseMigrator.export_schema_to_mysql(); print(f'Exported {len(ddls)} tables'); print(ddls[0][:200] if ddls else 'no tables')"`
Expected: Prints exported table count and first DDL snippet

- [ ] **Step 3: Commit**

```bash
git add app/models/db_migration.py
git commit -m "feat: add DatabaseMigrator.export_schema_to_mysql()"
```

---

### Task 11: 数据库迁移工具——数据迁移和验证

**Files:**
- Modify: `app/models/db_migration.py` — 添加数据迁移方法

- [ ] **Step 1: 添加数据迁移方法**

在 `DatabaseMigrator` 类中补充：

```python
    @staticmethod
    def migrate_table_data(
        table_name: str,
        mysql_params: dict,
        batch_size: int = 1000,
    ) -> tuple[int, int]:
        """Migrate one table: returns (success_rows, failed_rows)."""
        import pymysql
        from app.models.errors import log_error

        success = 0
        failed = 0

        with _sqlite_raw_connect() as sqlite_conn:
            total = sqlite_conn.execute(
                f"SELECT COUNT(*) as cnt FROM {table_name}"
            ).fetchone()["cnt"]
            if total == 0:
                return 0, 0

            columns_info = sqlite_conn.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()
            columns = [c["name"] for c in columns_info]

            for offset in range(0, total, batch_size):
                rows = sqlite_conn.execute(
                    f"SELECT * FROM {table_name} LIMIT ? OFFSET ?",
                    (batch_size, offset),
                ).fetchall()
                if not rows:
                    break

                try:
                    mysql_conn = pymysql.connect(
                        host=str(mysql_params["host"]),
                        port=int(mysql_params["port"]),
                        user=str(mysql_params["user"]),
                        password=str(mysql_params["password"]),
                        database=str(mysql_params["database"]),
                        cursorclass=pymysql.cursors.DictCursor,
                        connect_timeout=10,
                    )
                    placeholders = ", ".join(["%s"] * len(columns))
                    cols_str = ", ".join(columns)
                    sql = f"INSERT IGNORE INTO {table_name}({cols_str}) VALUES({placeholders})"

                    with mysql_conn.cursor() as cursor:
                        values = [tuple(dict(r).values()) for r in rows]
                        cursor.executemany(sql, values)
                    mysql_conn.commit()
                    mysql_conn.close()
                    success += len(rows)
                except Exception as e:
                    log_error(f"migrate_table_data {table_name} offset={offset}", e)
                    failed += len(rows)

        return success, failed

    @staticmethod
    async def migrate_all_tables(
        mysql_params: dict,
    ) -> dict[str, tuple[int, int]]:
        """Migrate all tables; returns {table: (success, failed)}."""
        from tornado.ioloop import IOLoop

        with _sqlite_raw_connect() as conn:
            all_tables = [
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master"
                    " WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            ]

        results: dict[str, tuple[int, int]] = {}
        for table in all_tables:
            s, f = await IOLoop.current().run_in_executor(
                None,
                DatabaseMigrator.migrate_table_data,
                table,
                mysql_params,
                1000,
            )
            results[table] = (s, f)
        return results
```

- [ ] **Step 2: 检查类型**

```bash
uv run ruff check app/models/db_migration.py
uv run pyright app/models/db_migration.py
```

- [ ] **Step 3: Commit**

```bash
git add app/models/db_migration.py
git commit -m "feat: add batch data migration and verify methods to DatabaseMigrator"
```

---

### Task 12: 增强db_switcher——添加静态便捷方法

**Files:**
- Modify: `app/models/db_switcher.py`

- [ ] **Step 1: 添加validate_mysql_connection, switch_to_mysql, switch_to_sqlite, get_migration_status**

在文件末尾（`DatabaseSwitcher` 类之后）添加模块级函数：

```python
# app/models/db_switcher.py 末尾添加:

def validate_mysql_connection(params: dict) -> tuple[bool, str]:
    """Validate MySQL connection params without side effects."""
    import pymysql
    try:
        conn = pymysql.connect(
            host=str(params["host"]),
            port=int(params["port"]),
            user=str(params["user"]),
            password=str(params["password"]),
            database=str(params["database"]),
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
        )
        conn.close()
        return True, "连接成功"
    except Exception as e:
        return False, f"连接失败: {e}"


def switch_to_mysql(params: dict) -> tuple[bool, str]:
    """Hot-switch to MySQL with preflight validation."""
    ok, msg = validate_mysql_connection(params)
    if not ok:
        return False, msg
    try:
        switcher = DatabaseSwitcher("mysql", params)
        switcher.run()
        return True, "已切换到MySQL"
    except Exception as e:
        return False, f"切换失败: {e}"


def switch_to_sqlite() -> tuple[bool, str]:
    """Hot-switch back to SQLite."""
    try:
        switcher = DatabaseSwitcher("sqlite")
        switcher.run()
        return True, "已切换到SQLite"
    except Exception as e:
        return False, f"切换失败: {e}"


def get_migration_status() -> dict:
    """Return current database configuration state."""
    import app.models.db as db_module
    return {
        "active_db": db_module._active_db_type,
        "mysql_configured": bool(db_module._mysql_params),
        "switch_lock_held": db_module._switch_lock.locked(),
    }
```

- [ ] **Step 2: 检查**

```bash
uv run ruff check app/models/db_switcher.py
uv run pyright app/models/db_switcher.py
uv run pytest test/test_db_switcher.py -v
```

- [ ] **Step 3: Commit**

```bash
git add app/models/db_switcher.py
git commit -m "feat: add static helper methods for web UI migration control"
```

---

### Task 13: 数据库迁移管理页面——控制器和路由

**Files:**
- Create: `app/controllers/db_migration.py`
- Modify: `app.py`

- [ ] **Step 1: 创建控制器**

```python
"""Database migration admin handler."""

from app.controllers.admin import AdminBaseHandler
from app.models.db_switcher import (
    get_migration_status,
    switch_to_mysql,
    switch_to_sqlite,
)
from app.models.db_migration import DatabaseMigrator
from app.models.db import _load_mysql_params, _sqlite_raw_connect


class AdminDbMigrationHandler(AdminBaseHandler):
    def get(self):
        status = get_migration_status()
        with _sqlite_raw_connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            table_stats = []
            for t in tables:
                cnt = conn.execute(
                    f"SELECT COUNT(*) as n FROM [{t['name']}]"
                ).fetchone()["n"]
                table_stats.append({"name": t["name"], "rows": cnt})

        self.render(
            "admin/db_migration.html",
            title="数据库迁移",
            username=self.current_user,
            status=status,
            table_stats=table_stats,
            msg=self._message(),
        )

    def post(self):
        action = self.get_body_argument("action", "")
        if action == "export_schema":
            return self._export_schema()
        if action == "migrate_data":
            return self._migrate_data()
        if action == "switch_to_mysql":
            return self._switch_to_mysql()
        if action == "switch_to_sqlite":
            return self._switch_to_sqlite()
        self.set_status(400)
        self.write({"error": "未知操作"})

    def _export_schema(self):
        ddls = DatabaseMigrator.export_schema_to_mysql()
        self.set_header("Content-Type", "text/plain; charset=utf-8")
        self.write("\n\n".join(ddls))

    async def _migrate_data(self):
        params = _load_mysql_params()
        if not params.get("host"):
            self.set_status(400)
            return self.write({"error": "MySQL未配置，请先在系统设置中配置"})
        results = await DatabaseMigrator.migrate_all_tables(params)
        total_s = sum(v[0] for v in results.values())
        total_f = sum(v[1] for v in results.values())
        self.write({"ok": True, "success": total_s, "failed": total_f})

    def _switch_to_mysql(self):
        params = _load_mysql_params()
        ok, msg = switch_to_mysql(params)
        if ok:
            self.write({"ok": True, "message": msg})
        else:
            self.set_status(500)
            self.write({"error": msg})

    def _switch_to_sqlite(self):
        ok, msg = switch_to_sqlite()
        if ok:
            self.write({"ok": True, "message": msg})
        else:
            self.set_status(500)
            self.write({"error": msg})
```

- [ ] **Step 2: 注册路由**

在 `app.py` 中添加导入和路由:
```python
from app.controllers.db_migration import AdminDbMigrationHandler
# routes列表中添加:
(r"/admin/db-migration", AdminDbMigrationHandler),
```

- [ ] **Step 3: 创建后台管理模板**

创建 `app/templates/admin/db_migration.html`:
```html
{% extends "admin/base.html" %}
{% block body %}
<div class="container-fluid p-4">
  <h4>数据库迁移管理</h4>
  <div class="card mb-3">
    <div class="card-body">
      <p>当前数据库: <strong>{{ status['active_db'] }}</strong></p>
      <div class="btn-group">
        <button class="btn btn-outline-primary" onclick="postAction('export_schema')">导出MySQL结构</button>
        <button class="btn btn-outline-warning" onclick="postAction('migrate_data')">执行数据迁移</button>
        <button class="btn btn-outline-success" onclick="postAction('switch_to_mysql')">切换到MySQL</button>
        <button class="btn btn-outline-secondary" onclick="postAction('switch_to_sqlite')">切回SQLite</button>
      </div>
    </div>
  </div>
  <h5>各表数据统计</h5>
  <table class="table table-sm table-striped">
    <thead><tr><th>表名</th><th>行数</th></tr></thead>
    <tbody>
      {% for t in table_stats %}
      <tr><td>{{ t['name'] }}</td><td>{{ t['rows'] }}</td></tr>
      {% end %}
    </tbody>
  </table>
</div>
<script>
function getXsrf() {
  const m = document.cookie.match(/_xsrf=([^;]+)/);
  return m ? m[1] : '';
}
function postAction(action) {
  const body = new URLSearchParams({action: action, _xsrf: getXsrf()}).toString();
  fetch('/admin/db-migration', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body})
    .then(r => r.json().then(d => alert(JSON.stringify(d, null, 2))))
    .catch(e => alert('请求失败: ' + e));
}
</script>
{% end %}
```

- [ ] **Step 4: 检查**

```bash
uv run ruff check app/controllers/db_migration.py
uv run pyright app/controllers/db_migration.py
uv run python scripts/check_templates.py
```

- [ ] **Step 5: Commit**

```bash
git add app/controllers/db_migration.py app.py app/templates/admin/db_migration.html
git commit -m "feat: add database migration admin page with schema export and hot-switch"
```

---

## 轮次2：模块2 + 4（依赖模块1）

---

### Task 14: 动态并发执行器

**Files:**
- Create: `app/agents/concurrent_executor.py`

- [ ] **Step 1: 创建concurrent_executor.py**

```python
"""Adaptive concurrent executor based on system load."""

import asyncio
from typing import Any


class ConcurrentExecutor:
    """Run coroutines concurrently with adaptive concurrency limits."""

    def __init__(self, max_concurrency: str | int = "dynamic") -> None:
        self._max = max_concurrency

    def _optimal(self) -> int:
        if isinstance(self._max, int):
            return self._max
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory().percent
        except Exception:
            return 3
        if cpu < 50 and mem < 70:
            return 10
        if cpu < 75 and mem < 85:
            return 5
        return 2

    async def run_concurrent(self, coroutines: list) -> list:
        if not coroutines:
            return []
        limit = self._optimal()
        sem = asyncio.Semaphore(limit)

        async def _bounded(coro):
            async with sem:
                return await coro

        results = await asyncio.gather(
            *[_bounded(c) for c in coroutines], return_exceptions=True
        )
        out: list = []
        for r in results:
            if isinstance(r, BaseException):
                out.append({"ok": False, "error": str(r)})
            else:
                out.append(r)
        return out
```

- [ ] **Step 2: 检查**

```bash
uv run ruff check app/agents/concurrent_executor.py
uv run pyright app/agents/concurrent_executor.py
```

- [ ] **Step 3: Commit**

```bash
git add app/agents/concurrent_executor.py
git commit -m "feat: add adaptive concurrent executor with load-based limits"
```

---

### Task 15: TaskAgent——状态机和数据结构

**Files:**
- Create: `app/agents/task_agent.py`

- [ ] **Step 1: 创建task_agent.py**

```python
"""TaskAgent — autonomous multi-step agent with planning + concurrent execution."""

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.models.errors import log_error


class TaskState(Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SubTask:
    id: str
    description: str
    tool_name: str
    args: dict[str, Any]
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    result: Any = None
    error: str | None = None


class TaskAgent:
    def __init__(
        self,
        user_text: str,
        model_row: dict[str, Any],
        allowed_tools: list[str] | None = None,
        max_iterations: int = 8,
        enable_reflection: bool = True,
        stream_cb: Any = None,
    ) -> None:
        self.user_text = user_text
        self.model_row = model_row
        self.allowed_tools = allowed_tools
        self.max_iterations = max_iterations
        self.enable_reflection = enable_reflection
        self.stream_cb = stream_cb
        self.state = TaskState.PLANNING
        self.tasks: list[SubTask] = []
        self.iteration = 0

    async def _emit(self, event_type: str, data: Any) -> None:
        if self.stream_cb:
            try:
                await self.stream_cb(event_type, data)
            except Exception:
                pass

    async def run(self) -> str:
        while self.iteration < self.max_iterations:
            self.iteration += 1
            if self.state == TaskState.PLANNING:
                await self._planning_phase()
            elif self.state == TaskState.EXECUTING:
                await self._executing_phase()
            elif self.state == TaskState.VALIDATING:
                await self._validating_phase()
            elif self.state == TaskState.REFLECTING:
                await self._reflecting_phase()
            elif self.state == TaskState.COMPLETED:
                return self._format_result()
            elif self.state == TaskState.FAILED:
                failed = [t for t in self.tasks if t.status == "failed"]
                reasons = "; ".join(t.error or "未知" for t in failed[:3])
                return f"任务失败: {reasons}"
            await asyncio.sleep(0.05)
        return "任务达到最大迭代次数限制"

    def _build_tools_desc(self) -> str:
        from app.agents.tool_registry import TOOLS
        tools = TOOLS
        if self.allowed_tools is not None:
            tools = [t for t in TOOLS if t["function"]["name"] in self.allowed_tools]
        lines = [f"- {t['function']['name']}: {t['function']['description']}" for t in tools]
        return "\n".join(lines)

    async def _planning_phase(self) -> None:
        await self._emit("planning", "分析任务并制定执行计划...")
        tools_desc = self._build_tools_desc()
        prompt = (
            f"你是任务规划专家。用户需求:\n{self.user_text}\n\n"
            f"可用工具:\n{tools_desc}\n\n"
            "请将需求分解为子任务，返回纯JSON（不要markdown标记）:\n"
            '{"tasks":[{"id":"task_1","description":"...","tool_name":"...","args":{...},"dependencies":[]}]}'
        )
        try:
            from app.models.model_client import chat_complete, parse_chat_response

            resp = await chat_complete(
                str(self.model_row["base_url"]),
                str(self.model_row["api_key"]),
                str(self.model_row["model_id"]),
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
                stream=False,
            )
            raw = await resp.aread()
            parsed = parse_chat_response(raw)
            content = str(parsed.get("content", "{}")).strip()
            content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            plan: dict = json.loads(content)
            for td in plan.get("tasks", []):
                tname = td.get("tool_name", "")
                if self.allowed_tools and tname not in self.allowed_tools:
                    continue
                self.tasks.append(SubTask(
                    id=td.get("id", f"task_{len(self.tasks)+1}"),
                    description=td.get("description", ""),
                    tool_name=tname,
                    args=td.get("args", {}),
                    dependencies=td.get("dependencies", []),
                ))
            await self._emit("plan_ready", f"计划完成: {len(self.tasks)}个子任务")
            self.state = TaskState.EXECUTING
        except Exception as e:
            log_error("TaskAgent._planning_phase", e)
            await self._emit("error", f"规划失败: {e}")
            self.state = TaskState.FAILED

    async def _executing_phase(self) -> None:
        await self._emit("executing", f"执行{len(self.tasks)}个子任务...")
        from app.agents.concurrent_executor import ConcurrentExecutor
        from app.agents.tool_executor import execute as tool_execute

        executor = ConcurrentExecutor("dynamic")
        completed_ids: set[str] = set()
        pending = list(self.tasks)

        while pending:
            ready = [t for t in pending if all(d in completed_ids for d in t.dependencies)]
            if not ready:
                for t in pending:
                    t.status = "failed"
                    t.error = "依赖无法满足"
                break

            async def _run_one(t: SubTask) -> dict:
                t.status = "running"
                await self._emit("task_start", f"开始: {t.description}")
                try:
                    t.result = await tool_execute(t.tool_name, t.args)
                    t.status = "completed"
                    await self._emit("task_done", f"完成: {t.description}")
                except Exception as e:
                    t.status = "failed"
                    t.error = str(e)
                    await self._emit("task_fail", f"失败: {t.description} - {e}")
                return {"ok": t.status == "completed", "error": t.error}

            await executor.run_concurrent([_run_one(t) for t in ready])
            for t in ready:
                completed_ids.add(t.id)
                pending.remove(t)

        failed = [t for t in self.tasks if t.status == "failed"]
        self.state = TaskState.REFLECTING if (failed and self.enable_reflection) else TaskState.VALIDATING

    async def _validating_phase(self) -> None:
        failed = [t for t in self.tasks if t.status == "failed"]
        if failed:
            await self._emit("validation", f"{len(failed)}个子任务失败")
            self.state = TaskState.REFLECTING if self.enable_reflection else TaskState.FAILED
        else:
            completed = [t for t in self.tasks if t.status == "completed"]
            await self._emit("validation", f"所有{len(completed)}个子任务完成")
            self.state = TaskState.COMPLETED

    async def _reflecting_phase(self) -> None:
        if self.iteration >= self.max_iterations - 1:
            await self._emit("reflection", "已达最大迭代次数")
            self.state = TaskState.COMPLETED
            return
        for t in self.tasks:
            if t.status == "failed":
                t.status = "pending"
                t.error = None
        await self._emit("reflection", "重试失败的任务")
        self.state = TaskState.EXECUTING

    def _format_result(self) -> str:
        parts: list[str] = []
        for t in self.tasks:
            if t.status == "completed":
                parts.append(f"## {t.description}\n{str(t.result)[:500]}")
        return "\n\n".join(parts) if parts else "任务完成，但无有效结果"
```

- [ ] **Step 2: 检查**

```bash
uv run ruff check app/agents/task_agent.py
uv run pyright app/agents/task_agent.py
```

- [ ] **Step 3: Commit**

```bash
git add app/agents/task_agent.py
git commit -m "feat: add complete TaskAgent with planning/executing/validating/reflecting phases"
```

---

### Task 16: 深度采集并发化

**Files:**
- Modify: `app/controllers/deep.py` — `_run_deep_collect` 方法

- [ ] **Step 1: 将串行循环改为并发执行**

在 `app/controllers/deep.py` 的 `_run_deep_collect` 方法中:

```python
    async def _run_deep_collect(self, task_id: int, item_ids: list[int]) -> None:
        """Run deep collection with concurrent execution."""
        from app.agents.concurrent_executor import ConcurrentExecutor

        model = DeepRepository.get_default_model()
        completed = 0
        failed = 0
        lock = __import__("asyncio").Lock()

        async def _process_one(item_id: int, crawler=None) -> None:
            nonlocal completed, failed
            try:
                DeepRepository.add_task_log(task_id, f"正在采集条目 #{item_id}...")
                result = await DeepRepository.collect_single_item(item_id, model, crawler)
                async with lock:
                    if result["ok"]:
                        DeepRepository.save_deep_result(item_id, task_id, result)
                        completed += 1
                        DeepRepository.add_task_log(
                            task_id, f"条目 #{item_id} 采集成功: {result.get('title', '')[:30]}"
                        )
                    else:
                        failed += 1
                        DeepRepository.add_task_log(
                            task_id, f"条目 #{item_id} 采集失败: {result.get('error', '未知错误')}"
                        )
                    DeepRepository.update_task_progress(task_id, completed, failed)
            except Exception as e:
                async with lock:
                    failed += 1
                    DeepRepository.add_task_log(task_id, f"条目 #{item_id} 异常: {str(e)[:100]}")
                    DeepRepository.update_task_progress(task_id, completed, failed)

        executor = ConcurrentExecutor("dynamic")
        try:
            from crawl4ai import AsyncWebCrawler
            async with AsyncWebCrawler(verbose=False) as crawler:
                coros = [_process_one(item_id, crawler) for item_id in item_ids]
                await executor.run_concurrent(coros)
        except Exception as crawler_err:
            DeepRepository.add_task_log(
                task_id, f"共享爬虫初始化失败，降级为独立模式: {str(crawler_err)[:100]}"
            )
            coros = [_process_one(item_id) for item_id in item_ids]
            await executor.run_concurrent(coros)

        if failed == 0:
            DeepRepository.complete_task(task_id)
        else:
            DeepRepository.complete_task(task_id)
            DeepRepository.add_task_log(task_id, f"采集完成: 成功{completed}, 失败{failed}")
```

- [ ] **Step 2: 检查**

```bash
uv run ruff check app/controllers/deep.py
uv run pyright app/controllers/deep.py
```

- [ ] **Step 3: Commit**

```bash
git add app/controllers/deep.py
git commit -m "feat: parallelize deep collection with ConcurrentExecutor"
```

---

### Task 17: 激活ChatSendHandler中的TaskAgent路由

**Files:**
- Modify: `app/controllers/chat.py`

- [ ] **Step 1: 替换agent_loop调用为条件路由**

在顶部添加导入:
```python
from app.agents.task_agent import TaskAgent
```

在 `ChatSendHandler.post()` 的流式响应部分（约第399行），替换:
```python
            await agent_loop.run(user_text, messages, model_row, _sse)
```
为:
```python
            if route_result["mode"] == "task_agent":
                await TaskAgent(
                    user_text=route_result["cleaned_text"],
                    model_row=model_row,
                    allowed_tools=allowed_tools,
                    max_iterations=route_result.get("task_config", {}).get("max_iterations", 8),
                    enable_reflection=route_result.get("task_config", {}).get("enable_reflection", True),
                    stream_cb=_sse,
                ).run()
            else:
                await agent_loop.run(
                    route_result["cleaned_text"], messages, model_row, _sse,
                    allowed_tools=allowed_tools,
                )
```

- [ ] **Step 2: 检查全部**

```bash
uv run ruff check app/controllers/chat.py
uv run ruff format app/controllers/chat.py
uv run pyright app/controllers/chat.py
```

- [ ] **Step 3: 运行全部测试**

Run: `uv run pytest test/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add app/controllers/chat.py
git commit -m "feat: activate TaskAgent routing via /task prefix in chat"
```

---

## 轮次3：模块6（集成与质量门禁）

---

### Task 18: 对话UI——添加/task快捷按钮

**Files:**
- Modify: `app/templates/web/chat.html`

- [ ] **Step 1: 在输入区添加/task按钮**

在发送按钮旁添加:

```html
<button type="button" class="btn btn-sm btn-outline-info ms-1"
  onclick="prependTask()" title="TaskAgent多步任务模式">
  /task
</button>
```

```javascript
function prependTask() {
  var inp = document.querySelector('textarea[name="message"], #message-input');
  if (!inp) return;
  if (inp.value.indexOf('/task') !== 0) {
    inp.value = '/task ' + inp.value;
  }
  inp.focus();
}
```

- [ ] **Step 2: 检查模板**

```bash
uv run python scripts/check_templates.py
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/web/chat.html
git commit -m "feat: add /task quick-insert button in chat UI"
```

---

### Task 19: 全量质量门禁

**Files:** 全部修改的文件

- [ ] **Step 1: 运行全部检查**

```bash
uv run ruff check .                        # 0 errors
uv run ruff format .                       # no changes needed
uv run pyright                             # 0 errors, 0 warnings
npx @biomejs/biome check                   # 0 errors
npx eslint app/static/js/ app/templates/ --ext .html,.js
uv run python scripts/check_templates.py   # 0 issues
```

- [ ] **Step 2: 运行全部测试**

```bash
uv run pytest test/ -v
```
Expected: All tests pass

- [ ] **Step 3: 启动服务器手动验证**

```bash
uv run python app.py
```

验证清单:
- [ ] 数据库 `database/app.db` 自动创建
- [ ] 后台登录 admin/admin888
- [ ] 数字员工页面可配置技能
- [ ] 对话输入 `/task 搜索XX新闻` 触发TaskAgent
- [ ] 瞭望采集源可采集到数据
- [ ] 深度采集多条数据并发运行
- [ ] `/admin/db-migration` 正确显示数据库状态

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "chore: quality gate — all checks pass, agentic enhancement complete"
```

---

## 附录A：文件清单总览

| 文件 | 操作 | 模块 |
|------|------|------|
| `app/models/db.py` | 修改DB_PATH + watchtower_logs表 | 通用前置 |
| `app/models/intent_router.py` | **新建** | 模块1 |
| `app/models/employee.py` | 修改 + get_employee_with_tools | 模块1 |
| `app/agents/agent_loop.py` | 修改 + allowed_tools | 模块1 |
| `app/controllers/chat.py` | 修改 + 路由集成 | 模块1+2 |
| `app/models/watchtower_scraper.py` | 重构selector+反爬+日志 | 模块3 |
| `app/models/db_migration.py` | **新建** | 模块5 |
| `app/models/db_switcher.py` | 修改 + 静态方法 | 模块5 |
| `app/controllers/db_migration.py` | **新建** | 模块5 |
| `app/templates/admin/db_migration.html` | **新建** | 模块5 |
| `app/agents/concurrent_executor.py` | **新建** | 模块2 |
| `app/agents/task_agent.py` | **新建** | 模块2 |
| `app/controllers/deep.py` | 修改 + 并发执行 | 模块4 |
| `app/templates/web/chat.html` | 修改 + /task按钮 | 模块6 |

## 附录B：回滚方案

```python
# TaskAgent回退：在ChatSendHandler中强制agent_loop
route_result["mode"] = "direct"

# 并发降级：在ConcurrentExecutor中固定低并发
def _optimal(self): return 2

# 数据库回滚：命令行一键切回
uv run python -c "from app.models.db_switcher import switch_to_sqlite; print(switch_to_sqlite())"
```

