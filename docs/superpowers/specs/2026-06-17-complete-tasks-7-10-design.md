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
