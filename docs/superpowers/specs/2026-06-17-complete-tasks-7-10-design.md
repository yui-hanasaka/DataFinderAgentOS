# 完成任务7-10功能设计文档

**日期**: 2026-06-17  
**作者**: Claude Code  
**版本**: v1.0

---

## 1. 项目背景

智能数据瞭望与智能问数系统已完成任务1-6（后台管理基础功能），当前需要完成剩余核心业务功能：

- **任务7**: 瞭望采集 - 智能数据采集接口
- **任务8**: 数据仓库 - 采集数据管理
- **任务9**: 深度采集 - crawl4ai深度解析
- **任务10**: 用户侧 - 注册与AI问数

本设计采用**顺序实现策略**，确保数据流从采集→仓库→深度分析→用户查询的完整闭环。

---

## 2. 整体架构

### 2.1 数据流管道

```
[瞭望采集] User输入关键词
    ↓ SSE实时流式采集
[临时结果] 用户选择条目
    ↓ 批量保存
[数据仓库] watchtower_items表
    ↓ 触发深度采集
[深度采集] crawl4ai + AI提取
    ↓ 保存全文
[数据仓库] data_warehouse表 (关联watchtower_items)
    ↓ 用户查询
[AI问数] 意图识别 → SQL/通用对话
```

### 2.2 技术选型

| 功能模块 | 技术方案 | 理由 |
|---------|---------|------|
| 实时通信 | SSE (Server-Sent Events) | Tornado原生支持，单向流适合进度推送 |
| 异步任务 | Tornado IOLoop + asyncio | 无需Redis/Celery，轻量级部署 |
| 网页采集 | requests + BeautifulSoup | 稳定可靠，适合静态页面 |
| 深度采集 | crawl4ai | 异步库，支持JS渲染，提取clean markdown |
| 意图识别 | 规则引擎 (关键词匹配) | 快速准确，无LLM调用延迟 |
| 密码加密 | PBKDF2-SHA256 | 已有实现，保持一致 |

---

## 3. 任务7: 瞭望采集

### 3.1 功能需求

1. **搜索引擎风格界面**: 大输入框，炫酷深色主题，区别于ZUI企业风格
2. **动态数据源选择**: Toggle开关，预选→自动开始→实时调整
3. **参数配置**: 每次采集数量（默认50）、页数（默认3）
4. **实时结果展示**: 3列网格卡片，自动分页，显示进度
5. **批量操作**: 多选/全选，保存到watchtower_items

### 3.2 UI设计

**页面布局** (`admin/watchtower_collect.html`):

```
┌─────────────────────────────────────────────────────────┐
│  智能数据瞭望                                            │
│  ┌───────────────────────────────────────────────────┐  │
│  │ 🔍 输入关键词开始采集...               [清空]    │  │
│  └───────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│  数据源选择:                                            │
│  ● 百度新闻  ○ 数据源2  ○ 数据源3  [管理数据源]        │
├─────────────────────────────────────────────────────────┤
│  采集配置:  每次 [50▼] 条  共 [3▼] 页                 │
├─────────────────────────────────────────────────────────┤
│  [████████░░░░] 60% | 已采集 90/150 | 耗时 12s         │
├─────────────────────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                  │
│  │☑ 标题1  │ │☑ 标题2  │ │☐ 标题3  │  ← 3列网格       │
│  │来源:百度│ │来源:百度│ │来源:百度│                  │
│  │2026-... │ │2026-... │ │2026-... │                  │
│  │摘要...  │ │摘要...  │ │摘要...  │                  │
│  └─────────┘ └─────────┘ └─────────┘                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                  │
│  │☐ 标题4  │ │☑ 标题5  │ │☐ 标题6  │                  │
│  └─────────┘ └─────────┘ └─────────┘                  │
├─────────────────────────────────────────────────────────┤
│  [◀] 第 1/5 页 [▶]  [☑全选] [保存选中(12条)]         │
└─────────────────────────────────────────────────────────┘
```

**视觉风格**:
- 深色渐变背景 (dark gradient: #0f0f23 → #1a1a3e)
- 毛玻璃卡片效果 (glassmorphism: backdrop-filter blur)
- 霓虹蓝强调色 (#00d9ff)
- 平滑动画 (CSS transitions 300ms)
- 独立于ZUI样式，科技感炫酷风格

### 3.3 数据库设计

**无需新表**，使用现有 `watchtower_sources` 和 `watchtower_items`。

**临时存储策略**: 采集结果先存入前端状态（JavaScript数组），用户选择后批量POST到后端保存。

### 3.4 后端实现

#### 3.4.1 路由设计

| 路由 | 方法 | Handler | 功能 |
|------|------|---------|------|
| `/admin/watchtower/collect` | GET | AdminWatchtowerCollectHandler | 渲染采集界面 |
| `/admin/watchtower/collect/stream` | GET | AdminWatchtowerCollectStreamHandler | SSE流式返回采集结果 |
| `/admin/watchtower/collect/save` | POST | AdminWatchtowerCollectSaveHandler | 批量保存选中条目 |

#### 3.4.2 采集器模块 (`app/models/watchtower_scraper.py`)

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
            
            items.append({
                'title': title_elem.get_text(strip=True),
                'url': title_elem.get('href', ''),
                'snippet': div.select_one('.c-font-normal')?.get_text(strip=True) or '',
                'source': div.select_one('.c-color-gray')?.get_text(strip=True) or '百度新闻',
                'published_time': div.select_one('.c-color-gray2')?.get_text(strip=True) or ''
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
```

#### 3.4.3 SSE流式Handler (`app/controllers/watchtower_collect.py`)

```python
class AdminWatchtowerCollectStreamHandler(AdminBaseHandler):
    async def get(self):
        """SSE流式返回采集结果"""
        self.set_header('Content-Type', 'text/event-stream')
        self.set_header('Cache-Control', 'no-cache')
        
        keyword = self.get_argument('keyword')
        source_ids = [int(x) for x in self.get_argument('sources').split(',')]
        pages = int(self.get_argument('pages', 3))
        limit = int(self.get_argument('limit', 50))
        
        total_items = 0
        total_expected = len(source_ids) * limit
        
        try:
            for idx, source_id in enumerate(source_ids):
                # 发送数据源开始事件
                self.write(f'event: source_start\ndata: {json.dumps({"source_id": source_id})}\n\n')
                await self.flush()
                
                # 采集数据源
                items = await WatchtowerScraper.scrape_source_async(source_id, keyword, pages, limit)
                
                # 逐个发送采集结果
                for item in items:
                    total_items += 1
                    item['id'] = f'temp_{total_items}'  # 临时ID
                    
                    self.write(f'event: item\ndata: {json.dumps(item)}\n\n')
                    await self.flush()
                    
                    # 发送进度
                    progress = int((total_items / total_expected) * 100)
                    self.write(f'event: progress\ndata: {json.dumps({"progress": progress, "count": total_items})}\n\n')
                    await self.flush()
            
            # 完成
            self.write(f'event: complete\ndata: {json.dumps({"total": total_items})}\n\n')
            await self.flush()
            
        except Exception as e:
            self.write(f'event: error\ndata: {json.dumps({"error": str(e)})}\n\n')
            await self.flush()

class AdminWatchtowerCollectSaveHandler(AdminBaseHandler):
    def post(self):
        """批量保存选中条目"""
        items = json.loads(self.get_body_argument('items'))
        
        saved_count = 0
        for item in items:
            try:
                WatchtowerRepository.insert_item({
                    'title': item['title'],
                    'url': item['url'],
                    'snippet': item['snippet'],
                    'source_name': item['source'],
                    'published_time': item['published_time'],
                    'collected_at': datetime.now().isoformat()
                })
                saved_count += 1
            except Exception as e:
                continue
        
        self.write({'success': True, 'saved': saved_count, 'total': len(items)})
```

### 3.5 前端交互

**JavaScript核心逻辑** (admin/watchtower_collect.html内嵌):

```javascript
let collectedItems = [];
let selectedIds = new Set();

// 监听关键词输入，Enter自动开始
document.getElementById('keyword').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') startCollection();
});

function startCollection() {
    const keyword = document.getElementById('keyword').value;
    const sources = Array.from(document.querySelectorAll('input[name="source"]:checked'))
                         .map(el => el.value).join(',');
    const pages = document.getElementById('pages').value;
    const limit = document.getElementById('limit').value;
    
    const url = `/admin/watchtower/collect/stream?keyword=${keyword}&sources=${sources}&pages=${pages}&limit=${limit}`;
    const eventSource = new EventSource(url);
    
    eventSource.addEventListener('item', (e) => {
        const item = JSON.parse(e.data);
        collectedItems.push(item);
        renderItem(item);
    });
    
    eventSource.addEventListener('progress', (e) => {
        const {progress, count} = JSON.parse(e.data);
        updateProgress(progress, count);
    });
    
    eventSource.addEventListener('complete', (e) => {
        eventSource.close();
        showNotification('采集完成！');
    });
}

function saveSelected() {
    const selected = collectedItems.filter(item => selectedIds.has(item.id));
    
    fetch('/admin/watchtower/collect/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({items: selected})
    })
    .then(res => res.json())
    .then(data => alert(`已保存 ${data.saved} 条数据`));
}
```

---

## 4. 任务8: 数据仓库

### 4.1 功能需求

1. 列表展示 `watchtower_items` 数据（20条/页）
2. 显示深度采集状态（未采集/采集中/已采集/失败）
3. 支持删除、批量删除、搜索
4. 触发深度采集（单条/批量）
5. 查看深度采集详情（已采集条目）

### 4.2 数据库修改

**扩展 `watchtower_items` 表**:

```sql
ALTER TABLE watchtower_items ADD COLUMN is_deep_collected INTEGER DEFAULT 0;
ALTER TABLE watchtower_items ADD COLUMN deep_task_id INTEGER DEFAULT NULL;
ALTER TABLE watchtower_items ADD COLUMN deep_collected_at TEXT DEFAULT NULL;
```

**关联关系**:
- `watchtower_items.deep_task_id` → `deep_tasks.id` (任务追踪)
- `data_warehouse.watchtower_item_id` → `watchtower_items.id` (内容存储)

### 4.3 UI设计

**仓库列表** (`admin/warehouse.html` - 增强现有页面):

```
┌──────────────────────────────────────────────────────────────┐
│ [搜索框...]  [批量删除] [批量深度采集]                       │
├──────────────────────────────────────────────────────────────┤
│ ☐ | 标题 | 来源 | 采集时间 | 状态 | 操作                      │
│───┼──────┼──────┼──────────┼──────┼──────────────────────────│
│ ☐ │新闻1 │百度  │06-17 10:20│ ✓已采│[查看详情] [重新采集]   │
│ ☐ │新闻2 │百度  │06-17 10:21│ ⊗未采│[深度采集] [删除]       │
│ ☐ │新闻3 │百度  │06-17 10:22│ ⏳采集中│[查看进度] [停止]    │
│ ☐ │新闻4 │百度  │06-17 10:23│ ✗失败│[重试] [删除]           │
│───┴──────┴──────┴──────────┴──────┴──────────────────────────│
│ 第 1/10 页 | 共 200 条 | 已选中 0 条                         │
└──────────────────────────────────────────────────────────────┘
```

**状态图标说明**:
- ✓ 已采集 (green, `is_deep_collected=1`)
- ⊗ 未采集 (gray, `is_deep_collected=0, deep_task_id=NULL`)
- ⏳ 采集中 (blue animated, `deep_task_id EXISTS, task.status='running'`)
- ✗ 失败 (red, `task.status='failed'`)

### 4.4 后端实现

**增强仓库Handler** (`app/controllers/warehouse.py`):

```python
class AdminWarehouseHandler(AdminBaseHandler):
    def get(self):
        """仓库列表 - 关联深度采集状态"""
        page = int(self.get_argument('page', 1))
        keyword = self.get_argument('q', '')
        
        # 联表查询
        items = WatchtowerRepository.get_items_with_deep_status(page, keyword)
        total = WatchtowerRepository.count_items(keyword)
        
        self.render('admin/warehouse.html', 
                    items=items, 
                    page=page, 
                    total=total)

class AdminWarehouseTriggerDeepHandler(AdminBaseHandler):
    async def post(self):
        """触发深度采集"""
        item_ids = json.loads(self.get_body_argument('item_ids'))
        
        # 创建深度采集任务
        task_id = DeepTaskRepository.create({
            'name': f'批量深度采集 {len(item_ids)} 条',
            'status': 'pending',
            'total_items': len(item_ids),
            'completed_items': 0,
            'failed_items': 0,
            'created_at': datetime.now().isoformat()
        })
        
        # 关联watchtower_items
        for item_id in item_ids:
            WatchtowerRepository.update_deep_task_id(item_id, task_id)
        
        # 异步启动采集
        IOLoop.current().spawn_callback(DeepCollector.collect_batch, item_ids, task_id)
        
        self.write({'success': True, 'task_id': task_id})

class AdminWarehouseDetailHandler(AdminBaseHandler):
    def get(self, item_id):
        """查看详情 - 显示深度采集内容"""
        item = WatchtowerRepository.get_item(int(item_id))
        deep_content = None
        
        if item['is_deep_collected']:
            deep_content = DataWarehouseRepository.get_by_watchtower_item(int(item_id))
        
        self.render('admin/warehouse_detail.html', 
                    item=item, 
                    deep_content=deep_content)
```

---

## 5. 任务9: 深度采集

### 5.1 功能需求

1. 使用 crawl4ai 抓取完整网页内容（支持JS渲染）
2. 调用默认AI模型提取/总结核心内容
3. 保存到 `data_warehouse` 表
4. 更新 `watchtower_items` 的深度采集标记
5. SSE实时进度推送（日志、统计）
6. 支持单条/批量采集
7. 失败重试机制（最多3次）

### 5.2 数据库设计

**扩展 `deep_tasks` 表**:

```sql
ALTER TABLE deep_tasks ADD COLUMN progress INTEGER DEFAULT 0;
ALTER TABLE deep_tasks ADD COLUMN total_items INTEGER DEFAULT 0;
ALTER TABLE deep_tasks ADD COLUMN completed_items INTEGER DEFAULT 0;
ALTER TABLE deep_tasks ADD COLUMN failed_items INTEGER DEFAULT 0;
ALTER TABLE deep_tasks ADD COLUMN logs TEXT DEFAULT '[]';
```

**`data_warehouse` 表结构** (已存在，复用):

```sql
CREATE TABLE IF NOT EXISTS data_warehouse (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watchtower_item_id INTEGER,  -- FK到watchtower_items
    title TEXT,
    url TEXT,
    raw_content TEXT,  -- crawl4ai抓取的完整markdown
    summary TEXT,      -- AI生成的摘要
    collected_at TEXT,
    FOREIGN KEY (watchtower_item_id) REFERENCES watchtower_items(id)
);
```

### 5.3 深度采集引擎

**采集器模块** (`app/models/deep_collector.py`):

```python
import asyncio
from crawl4ai import AsyncWebCrawler
from app.models.model_client import ModelClient

class DeepCollector:
    MAX_RETRIES = 3
    
    @staticmethod
    async def collect_item(item_id: int, task_id: int, retry_count: int = 0):
        """采集单个条目"""
        try:
            # 获取条目
            item = WatchtowerRepository.get_item(item_id)
            DeepTaskRepository.add_log(task_id, f'开始采集: {item["title"]}')
            
            # 使用crawl4ai深度抓取
            async with AsyncWebCrawler(verbose=False) as crawler:
                result = await crawler.arun(
                    url=item['url'],
                    word_count_threshold=10,
                    bypass_cache=True
                )
                raw_content = result.markdown
            
            # AI提取核心内容
            model = ModelRepository.get_default_model()
            summary_prompt = f"""请提取以下文章的核心内容，保留关键信息，去除广告和无关内容：

标题：{item['title']}
内容：{raw_content[:2000]}  # 限制长度避免超token

要求：
1. 保留文章主要观点和事实
2. 去除广告、推广、导航等无关内容
3. 输出格式为markdown
4. 字数控制在500字以内
"""
            
            summary = await ModelClient.chat_complete_simple(model, summary_prompt)
            
            # 保存到数据仓库
            warehouse_id = DataWarehouseRepository.insert({
                'watchtower_item_id': item_id,
                'title': item['title'],
                'url': item['url'],
                'raw_content': raw_content,
                'summary': summary,
                'collected_at': datetime.now().isoformat()
            })
            
            # 更新标记
            WatchtowerRepository.mark_deep_collected(item_id, task_id)
            
            # 记录成功
            DeepTaskRepository.add_log(task_id, f'✓ 采集成功: {item["title"]} (ID: {warehouse_id})')
            DeepTaskRepository.increment_completed(task_id)
            
            return True
            
        except Exception as e:
            # 重试逻辑
            if retry_count < DeepCollector.MAX_RETRIES:
                DeepTaskRepository.add_log(task_id, f'⚠ 重试 ({retry_count+1}/{DeepCollector.MAX_RETRIES}): {item["title"]} - {str(e)}')
                await asyncio.sleep(2 ** retry_count)  # 指数退避
                return await DeepCollector.collect_item(item_id, task_id, retry_count + 1)
            else:
                # 失败
                DeepTaskRepository.add_log(task_id, f'✗ 采集失败: {item["title"]} - {str(e)}')
                DeepTaskRepository.increment_failed(task_id)
                return False
    
    @staticmethod
    async def collect_batch(item_ids: list, task_id: int):
        """批量采集（并发控制）"""
        DeepTaskRepository.update_status(task_id, 'running')
        DeepTaskRepository.add_log(task_id, f'开始批量采集，共 {len(item_ids)} 条')
        
        # 限制并发数（避免过载）
        semaphore = asyncio.Semaphore(3)
        
        async def limited_collect(item_id):
            async with semaphore:
                return await DeepCollector.collect_item(item_id, task_id)
        
        results = await asyncio.gather(*[limited_collect(item_id) for item_id in item_ids])
        
        # 更新任务状态
        success_count = sum(results)
        failed_count = len(results) - success_count
        
        DeepTaskRepository.update_final_status(task_id, 'completed', 100)
        DeepTaskRepository.add_log(task_id, f'批量采集完成: 成功 {success_count}, 失败 {failed_count}')
```

### 5.4 进度推送Handler

**SSE进度Handler** (`app/controllers/deep_collect.py`):

```python
class AdminDeepCollectProgressHandler(AdminBaseHandler):
    async def get(self):
        """SSE推送采集进度"""
        task_id = int(self.get_argument('task_id'))
        self.set_header('Content-Type', 'text/event-stream')
        self.set_header('Cache-Control', 'no-cache')
        
        last_log_count = 0
        
        while True:
            task = DeepTaskRepository.get(task_id)
            logs = json.loads(task['logs'] or '[]')
            
            # 推送新日志
            new_logs = logs[last_log_count:]
            if new_logs:
                for log in new_logs:
                    self.write(f'event: log\ndata: {json.dumps(log)}\n\n')
                    await self.flush()
                last_log_count = len(logs)
            
            # 推送进度
            progress_data = {
                'progress': task['progress'],
                'completed': task['completed_items'],
                'failed': task['failed_items'],
                'total': task['total_items']
            }
            self.write(f'event: progress\ndata: {json.dumps(progress_data)}\n\n')
            await self.flush()
            
            # 检查完成
            if task['status'] in ('completed', 'failed'):
                self.write(f'event: complete\ndata: {json.dumps({"status": task["status"]})}\n\n')
                await self.flush()
                break
            
            await asyncio.sleep(1)
```

### 5.5 前端进度弹窗

**进度Modal** (admin/warehouse.html内嵌):

```html
<div id="deepCollectModal" class="modal">
    <div class="modal-content">
        <h3>深度采集进度</h3>
        <div class="progress-bar">
            <div id="progressFill" style="width: 0%"></div>
        </div>
        <p id="progressText">0% (0/0)</p>
        
        <div id="logContainer" style="max-height: 300px; overflow-y: auto;">
            <!-- 实时日志 -->
        </div>
        
        <div id="statsContainer">
            成功: <span id="successCount">0</span> | 
            失败: <span id="failCount">0</span> | 
            待处理: <span id="pendingCount">0</span>
        </div>
        
        <button onclick="closeModal()">关闭</button>
    </div>
</div>

<script>
function startDeepCollect(itemIds) {
    // 触发采集
    fetch('/admin/warehouse/trigger_deep', {
        method: 'POST',
        body: JSON.stringify({item_ids: itemIds})
    })
    .then(res => res.json())
    .then(data => {
        showModal();
        watchProgress(data.task_id);
    });
}

function watchProgress(taskId) {
    const eventSource = new EventSource(`/admin/deep/progress?task_id=${taskId}`);
    
    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        updateProgressBar(data.progress);
        updateStats(data);
    });
    
    eventSource.addEventListener('log', (e) => {
        const log = JSON.parse(e.data);
        appendLog(log);
    });
    
    eventSource.addEventListener('complete', (e) => {
        eventSource.close();
        showSuccessMessage();
    });
}
</script>
```

---

## 6. 任务10: 用户侧功能

### 6.1 用户注册

**新增路由**: `/user/register` (GET + POST)

**Handler实现** (`app/controllers/auth.py`):

```python
class RegisterHandler(BaseHandler):
    def get(self):
        if self.current_user:
            self.redirect('/home')
            return
        self.render('web/register.html', error=None)
    
    def post(self):
        username = self.get_body_argument('username')
        password = self.get_body_argument('password')
        confirm_password = self.get_body_argument('confirm_password')
        
        # 验证
        if not username or len(username) < 3:
            self.render('web/register.html', error='用户名至少3个字符')
            return
        
        if password != confirm_password:
            self.render('web/register.html', error='两次密码不一致')
            return
        
        if len(password) < 6:
            self.render('web/register.html', error='密码至少6个字符')
            return
        
        # 创建用户（普通用户role_id=2）
        try:
            user_id = UserRepository.create_user(username, password, role_id=2)
            self.set_secure_cookie('username', username)
            self.redirect('/home')
        except Exception as e:
            self.render('web/register.html', error='用户名已存在')
```

**注册页面** (`web/register.html`):

```html
{% extends "base.html" %}
{% block body %}
<div class="register-container">
    <form method="post">
        {% module xsrf_form_html() %}
        <h2>用户注册</h2>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% end %}
        <input type="text" name="username" placeholder="用户名（3-20字符）" required>
        <input type="password" name="password" placeholder="密码（至少6字符）" required>
        <input type="password" name="confirm_password" placeholder="确认密码" required>
        <button type="submit">注册</button>
        <p>已有账号？<a href="/user/login">去登录</a></p>
    </form>
</div>
{% end %}
```

### 6.2 意图识别系统

**意图分类器** (`app/models/intent_classifier.py`):

```python
class IntentClassifier:
    """规则引擎意图识别"""
    
    # 数据查询关键词
    SQL_KEYWORDS = [
        '数据库', '表', '查询', '统计', '分析', '数据', '记录', 
        '多少', '有多少', '几个', '几条', '总数', '数量',
        '列出', '显示', '查看', '所有', '全部',
        '用户', '会话', '消息', '模型', '采集'
    ]
    
    # 天气查询
    WEATHER_KEYWORDS = ['天气', '气温', '温度', '下雨', '晴天', '阴天', '下雪']
    
    # 音乐查询
    MUSIC_KEYWORDS = ['音乐', '歌曲', '播放', '歌手', '专辑', '听歌']
    
    @staticmethod
    def classify(user_query: str) -> dict:
        """
        分类用户意图
        
        返回: {
            'intent': 'sql' | 'weather' | 'music' | 'skill' | 'general',
            'confidence': 0.0-1.0,
            'matched_keywords': []
        }
        """
        query_lower = user_query.lower()
        
        # 1. 检查@前缀（技能调度）
        if '@' in user_query or user_query.startswith('\\'):
            return {
                'intent': 'skill',
                'confidence': 1.0,
                'matched_keywords': []
            }
        
        # 2. SQL数据查询
        sql_matches = [kw for kw in IntentClassifier.SQL_KEYWORDS if kw in query_lower]
        if len(sql_matches) >= 2:  # 至少匹配2个关键词
            return {
                'intent': 'sql',
                'confidence': min(len(sql_matches) * 0.25, 1.0),
                'matched_keywords': sql_matches
            }
        
        # 3. 天气查询
        weather_matches = [kw for kw in IntentClassifier.WEATHER_KEYWORDS if kw in query_lower]
        if weather_matches:
            return {
                'intent': 'weather',
                'confidence': 0.9,
                'matched_keywords': weather_matches
            }
        
        # 4. 音乐查询
        music_matches = [kw for kw in IntentClassifier.MUSIC_KEYWORDS if kw in query_lower]
        if music_matches:
            return {
                'intent': 'music',
                'confidence': 0.9,
                'matched_keywords': music_matches
            }
        
        # 5. 默认：通用对话
        return {
            'intent': 'general',
            'confidence': 0.5,
            'matched_keywords': []
        }
```

### 6.3 增强对话Handler

**SQL查询工具** (`app/models/sql_tool.py`):

```python
class SQLTool:
    """SQL查询工具 - 隐藏SQL语句，只返回自然语言结果"""
    
    SAFE_TABLES = [
        'users', 'chat_sessions', 'chat_messages', 
        'watchtower_items', 'data_warehouse', 'ai_models'
    ]
    
    @staticmethod
    async def execute_query(user_query: str, model_config: dict) -> str:
        """
        1. 调用AI生成SQL
        2. 执行SQL（安全检查）
        3. 格式化结果为自然语言
        """
        # 步骤1: 生成SQL
        schema_info = SQLTool._get_schema_info()
        sql_prompt = f"""你是SQL专家，根据用户问题生成SQLite查询语句。

可用表结构：
{schema_info}

用户问题：{user_query}

要求：
1. 只返回SQL语句，不要任何解释
2. 使用SELECT查询，禁止UPDATE/DELETE/DROP
3. 限制结果数量 LIMIT 100

SQL:"""
        
        sql_query = await ModelClient.chat_complete_simple(model_config, sql_prompt)
        sql_query = sql_query.strip().replace('```sql', '').replace('```', '').strip()
        
        # 步骤2: 安全检查
        if not SQLTool._is_safe_query(sql_query):
            return "❌ 查询请求包含不安全操作，已拒绝执行"
        
        # 步骤3: 执行SQL
        try:
            results = SQLTool._execute_sql(sql_query)
        except Exception as e:
            return f"❌ 查询执行失败：{str(e)}"
        
        # 步骤4: 格式化结果
        if not results:
            return "查询完成，但没有找到匹配的数据。"
        
        format_prompt = f"""将SQL查询结果转换为自然语言回答：

用户问题：{user_query}
查询结果：{json.dumps(results[:10], ensure_ascii=False)}  # 限制长度
结果总数：{len(results)} 条

要求：
1. 用清晰易懂的语言描述结果
2. 如果结果较多，总结关键信息
3. 不要提及SQL语句
"""
        
        answer = await ModelClient.chat_complete_simple(model_config, format_prompt)
        return answer
    
    @staticmethod
    def _is_safe_query(sql: str) -> bool:
        """安全检查：只允许SELECT，禁止修改操作"""
        sql_upper = sql.upper()
        dangerous = ['UPDATE', 'DELETE', 'DROP', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
        return sql_upper.startswith('SELECT') and not any(d in sql_upper for d in dangerous)
    
    @staticmethod
    def _execute_sql(sql: str) -> list:
        """执行SQL查询"""
        conn = get_connection()
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        conn.close()
        return results
    
    @staticmethod
    def _get_schema_info() -> str:
        """获取表结构信息"""
        conn = get_connection()
        tables_info = []
        
        for table in SQLTool.SAFE_TABLES:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [f"{row[1]} ({row[2]})" for row in cursor.fetchall()]
            tables_info.append(f"{table}: {', '.join(columns)}")
        
        conn.close()
        return '\n'.join(tables_info)
```

**增强聊天Handler** (`app/controllers/chat.py`):

```python
class ChatSendHandler(ChatBaseHandler):
    async def post(self):
        """处理用户消息 - 集成意图识别"""
        session_id = int(self.get_body_argument('session_id'))
        user_input = self.get_body_argument('message')
        model_id = int(self.get_body_argument('model_id', 0))
        
        self.set_header('Content-Type', 'text/event-stream')
        self.set_header('Cache-Control', 'no-cache')
        
        # 保存用户消息
        ChatRepository.add_message(session_id, 'user', user_input)
        
        # 意图识别
        intent_result = IntentClassifier.classify(user_input)
        
        try:
            # 根据意图路由
            if intent_result['intent'] == 'sql':
                # SQL查询
                model = ModelRepository.get_model(model_id) if model_id else ModelRepository.get_default_model()
                response = await SQLTool.execute_query(user_input, model)
                
                # 流式输出
                for char in response:
                    self.write(f'data: {json.dumps({"content": char})}\n\n')
                    await self.flush()
                    await asyncio.sleep(0.01)  # 模拟流式
                
                # 保存助手回复
                ChatRepository.add_message(session_id, 'assistant', response)
            
            elif intent_result['intent'] == 'skill':
                # 技能调度（现有逻辑）
                dispatch_result = SkillDispatcher.dispatch(user_input)
                response = await self._handle_skill(dispatch_result, session_id)
                # ... 流式输出
            
            else:
                # 通用对话
                model = ModelRepository.get_model(model_id) if model_id else ModelRepository.get_default_model()
                history = ChatRepository.get_session_messages(session_id)
                
                full_response = ''
                async for chunk in ModelClient.stream_chat(model, user_input, history):
                    content = chunk.get('content', '')
                    full_response += content
                    self.write(f'data: {json.dumps({"content": content})}\n\n')
                    await self.flush()
                
                # 保存助手回复
                ChatRepository.add_message(session_id, 'assistant', full_response)
        
        except Exception as e:
            error_msg = f'处理失败：{str(e)}'
            self.write(f'data: {json.dumps({"error": error_msg})}\n\n')
            await self.flush()
        
        # 完成
        self.write('data: [DONE]\n\n')
        await self.flush()
```

### 6.4 前端增强

**模型切换器** (web/chat.html):

```html
<div class="model-selector">
    <label>当前模型:</label>
    <select id="modelSelect" onchange="switchModel()">
        {% for model in available_models %}
        <option value="{{ model['id'] }}" {% if model['is_default'] %}selected{% end %}>
            {{ model['model_name'] }}
            {% if model['is_default'] %}(默认){% end %}
        </option>
        {% end %}
    </select>
</div>
```

**Markdown渲染** (引入marked.js):

```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
function renderMessage(content) {
    const html = marked.parse(content);
    return html;
}

// 处理SSE响应
eventSource.onmessage = (e) => {
    if (e.data === '[DONE]') {
        eventSource.close();
        return;
    }
    
    const data = JSON.parse(e.data);
    accumulatedContent += data.content;
    
    // 实时渲染markdown
    document.getElementById('messageArea').innerHTML = renderMessage(accumulatedContent);
};
</script>
```

---

## 7. 测试策略

### 7.1 单元测试

**测试文件**: `test/test_intent_classifier.py`

```python
def test_sql_intent():
    result = IntentClassifier.classify("数据库中有多少用户？")
    assert result['intent'] == 'sql'
    assert result['confidence'] > 0.5

def test_general_intent():
    result = IntentClassifier.classify("你好，今天天气怎么样？")
    assert result['intent'] in ('general', 'weather')
```

### 7.2 集成测试

**测试采集流程**:
1. 启动服务器
2. 访问 `/admin/watchtower/collect`
3. 输入关键词"西华师范大学"，开始采集
4. 验证SSE事件流
5. 检查 `watchtower_items` 表数据

**测试深度采集**:
1. 从仓库触发深度采集
2. 监听SSE进度
3. 验证 `data_warehouse` 表数据
4. 检查 `is_deep_collected` 标记

---

## 8. 部署清单

### 8.1 依赖安装

```bash
# 新增依赖
pip install crawl4ai beautifulsoup4 requests

# 或使用uv
uv pip install crawl4ai beautifulsoup4 requests
```

### 8.2 数据库迁移

执行SQL扩展脚本（在 `app/models/db.py` 的 `init_db()` 中添加）:

```python
def _migrate_tasks_7_10():
    """扩展表结构以支持任务7-10"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 扩展watchtower_items
    cursor.execute("""
        ALTER TABLE watchtower_items 
        ADD COLUMN is_deep_collected INTEGER DEFAULT 0
    """)
    cursor.execute("""
        ALTER TABLE watchtower_items 
        ADD COLUMN deep_task_id INTEGER DEFAULT NULL
    """)
    cursor.execute("""
        ALTER TABLE watchtower_items 
        ADD COLUMN deep_collected_at TEXT DEFAULT NULL
    """)
    
    # 扩展deep_tasks
    cursor.execute("""
        ALTER TABLE deep_tasks 
        ADD COLUMN progress INTEGER DEFAULT 0
    """)
    cursor.execute("""
        ALTER TABLE deep_tasks 
        ADD COLUMN total_items INTEGER DEFAULT 0
    """)
    cursor.execute("""
        ALTER TABLE deep_tasks 
        ADD COLUMN completed_items INTEGER DEFAULT 0
    """)
    cursor.execute("""
        ALTER TABLE deep_tasks 
        ADD COLUMN failed_items INTEGER DEFAULT 0
    """)
    cursor.execute("""
        ALTER TABLE deep_tasks 
        ADD COLUMN logs TEXT DEFAULT '[]'
    """)
    
    conn.commit()
    conn.close()
```

### 8.3 路由注册

在 `app.py` 中添加新路由:

```python
# 瞭望采集
(r'/admin/watchtower/collect', AdminWatchtowerCollectHandler),
(r'/admin/watchtower/collect/stream', AdminWatchtowerCollectStreamHandler),
(r'/admin/watchtower/collect/save', AdminWatchtowerCollectSaveHandler),

# 数据仓库增强
(r'/admin/warehouse/trigger_deep', AdminWarehouseTriggerDeepHandler),
(r'/admin/warehouse/(\d+)/detail', AdminWarehouseDetailHandler),

# 深度采集
(r'/admin/deep/progress', AdminDeepCollectProgressHandler),

# 用户注册
(r'/user/register', RegisterHandler),
```

---

## 9. 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| crawl4ai抓取失败（JS渲染、反爬） | 深度采集不完整 | 重试机制 + 降级到requests |
| AI模型调用超时 | 深度采集阻塞 | 设置timeout=30s，失败跳过 |
| 并发采集过多导致服务器卡顿 | 用户体验差 | Semaphore限制并发数=3 |
| SQL注入风险（用户构造恶意查询） | 数据泄露 | 白名单表 + 禁止修改操作 |
| 意图识别误判 | 用户体验差 | 增加关键词库 + 用户反馈机制 |

---

## 10. 未来优化方向

1. **意图识别升级**: 从规则引擎升级为LLM分类（调用默认模型判断意图）
2. **采集源管理**: 可视化编辑器，支持XPath/CSS选择器配置
3. **分布式采集**: 引入Celery + Redis，支持大规模并发
4. **智能去重**: 对采集结果做相似度检测，避免重复存储
5. **用户权限细化**: 不同角色访问不同数据仓库（数据隔离）

---

## 11. 总结

本设计完成了智能数据瞭望与问数系统的核心业务闭环：

- ✅ **瞭望采集**: SSE实时流式采集，炫酷搜索界面
- ✅ **数据仓库**: 统一管理采集数据，状态可视化
- ✅ **深度采集**: crawl4ai + AI提取，进度实时推送
- ✅ **用户侧**: 注册系统 + 意图识别 + SQL工具

技术选型遵循**轻量级原则**，基于Tornado + SQLite + SSE，无需额外中间件，满足中小规模部署需求。

---

**批准后续步骤**: 进入实施计划编写阶段（调用 writing-plans skill）
