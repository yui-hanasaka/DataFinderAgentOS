# DataFinderAgentOS Agentic架构增强设计

**日期**: 2026-06-18  
**作者**: Claude Code  
**方案**: 方案C（混合式轻量Agent）+ 并行多Agent开发 + 审计模式

---

## 一、背景与问题

### 1.1 当前问题

1. **数字员工技能系统不可用**：`digital_employees.skills`字段存储了技能ID，但agent_loop未读取该字段过滤工具
2. **深度采集串行执行**：多条目采集时顺序执行，用户全选10条需等待10x时间
3. **瞭望采集失败率高**：
   - CSS选择器失效（网站改版）
   - 反爬策略阻断（缺少headers）
   - 只采集到标题，内容缺失
4. **数据库迁移不完整**：
   - 数据库文件路径错误（`qq_monitors.db` vs `database/app.db`）
   - 缺少完整的SQLite→MySQL迁移工具
   - 热切换机制未经充分测试

### 1.2 设计目标

1. **数字员工技能可用**：员工配置的技能真正驱动工具调用
2. **深度采集并发化**：支持1-10动态并发，根据系统负载自适应
3. **瞭望采集稳定性提升**：多层selector回退，采集成功率从30%→80%+
4. **数据库迁移工具完善**：提供结构导出、数据迁移、热切换全流程
5. **引入TaskAgent**：用户通过`/task`前缀显式触发重型Agent模式

---

## 二、整体架构

### 2.1 系统分层

```
┌─────────────────────────────────────────────────┐
│  用户层（User Interface）                         │
│  - Web Chat界面（显式前缀触发）                    │
│  - Admin管理界面（后台任务触发）                   │
└─────────────┬───────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────┐
│  调度层（Dispatcher）                             │
│  - 意图识别：/task → TaskAgent                    │
│  - 简单对话 → 直接agent_loop                      │
│  - 数字员工技能映射 → 工具权限过滤                 │
└─────────────┬───────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────┐
│  执行层（Execution）                              │
│  ┌──────────────┐  ┌──────────────┐             │
│  │ agent_loop   │  │ TaskAgent    │             │
│  │ (现有轻量级)  │  │ (新增重型)    │             │
│  └──────────────┘  └──────────────┘             │
│                                                  │
│  ┌──────────────────────────────────┐           │
│  │ ConcurrentExecutor（动态并发）   │           │
│  │ - 自适应并发数控制                │           │
│  │ - 资源池管理（crawl4ai实例）      │           │
│  └──────────────────────────────────┘           │
└─────────────┬───────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────┐
│  工具层（Tools）                                  │
│  - watchtower_search, deep_collect, code_execute │
│  - 增强型爬虫（多selector回退）                    │
│  - AI内容提取器                                   │
└──────────────────────────────────────────────────┘
```

### 2.2 执行模式对比

| 特性 | agent_loop（现有） | TaskAgent（新增） |
|------|-------------------|-------------------|
| 触发方式 | 默认 | 用户输入`/task`前缀 |
| 任务分解 | ✗ | ✓ |
| 并发执行 | ✗ | ✓（动态1-10） |
| 自我验证 | ✗ | ✓ |
| 最大轮次 | 8轮 | 8轮 |
| Token消耗 | 低 | 中 |
| 适用场景 | 简单对话、单工具调用 | 多步骤任务、批量处理 |

---

## 三、调度层设计

### 3.1 意图路由

**文件**: `app/models/intent_router.py`（新增）

**触发关键字**：
- `/task` - 启动完整TaskAgent模式
- `/深度分析` - TaskAgent + 深度推理
- `/批量处理` - TaskAgent + 高并发执行

**路由逻辑**：
```python
def route_message(user_text: str, employee_id: int | None) -> dict:
    # 优先级：显式前缀 > 员工配置 > 默认direct
    if user_text.startswith("/task"):
        return {"mode": "task_agent", "cleaned_text": user_text[5:].strip()}
    
    if employee_id:
        employee = EmployeeRepository.get_employee(employee_id)
        if employee and employee["skills"].get("force_task_agent"):
            return {"mode": "task_agent", ...}
    
    return {"mode": "direct", ...}
```

### 3.2 数字员工技能映射

**问题根因**: `digital_employees.skills`字段存储skill_id数组，但未被agent_loop读取。

**解决方案**: 新增`get_employee_with_tools()`方法，将skill_id映射为tool_name列表。

**映射规则**:
```python
tool_mapping = {
    "web_search": "web_search",
    "code_exec": "code_execute",
    "watchtower": "watchtower_search",
    "warehouse": "warehouse_query",
    "deep_crawl": "deep_collect",
    "env_check": "env_info",
}
```

**调用流程**:
1. `ChatSendHandler` → 读取`employee_id`
2. `EmployeeRepository.get_employee_with_tools(employee_id)` → 返回`allowed_tools`列表
3. 传递给`agent_loop.run()`或`TaskAgent()`
4. 工具调用前过滤：如果`allowed_tools`非空且工具不在列表中，拒绝调用

---

## 四、TaskAgent执行层

### 4.1 核心状态机

**文件**: `app/agents/task_agent.py`（新增）

**状态定义**:
```python
class TaskState(Enum):
    PLANNING = "planning"      # 分解任务
    EXECUTING = "executing"    # 执行子任务
    VALIDATING = "validating"  # 验证结果
    REFLECTING = "reflecting"  # 反思与调整
    COMPLETED = "completed"    # 完成
    FAILED = "failed"          # 失败
```

**状态转换**:
```
PLANNING → EXECUTING → VALIDATING → COMPLETED
              ↓ (失败)        ↓ (失败)
         REFLECTING ←────────┘
              ↓ (重试)
         EXECUTING
```

### 4.2 Planning阶段：任务分解

**输入**: 用户需求文本  
**输出**: 子任务DAG（有向无环图）

**示例**:
```
用户: "/task 采集西华师范大学相关新闻并进行深度分析"

模型返回:
{
  "tasks": [
    {
      "id": "task_1",
      "description": "从瞭望系统搜索关键词'西华师范大学'",
      "tool_name": "watchtower_search",
      "args": {"keywords": "西华师范大学", "limit": 20},
      "dependencies": []
    },
    {
      "id": "task_2",
      "description": "对搜索结果中的前5条进行深度采集",
      "tool_name": "deep_collect",
      "args": {"url": "{{task_1.results[0].url}}"},
      "dependencies": ["task_1"]
    },
    ...
  ]
}
```

### 4.3 Executing阶段：并发执行

**核心组件**: `ConcurrentExecutor`

**并发策略**: 动态调整（1-10）
- CPU < 50% && Mem < 70% → 10并发
- CPU < 75% && Mem < 85% → 5并发
- 否则 → 2并发

**依赖解析**: 拓扑排序（Topological Sort）
- 无依赖的任务同层并发执行
- 有依赖的任务等待前置任务完成

**示例**:
```
Layer 1: [task_1]  # 搜索（无依赖）
         ↓ 完成后
Layer 2: [task_2, task_3, task_4, task_5, task_6]  # 5个deep_collect并发
```

### 4.4 Validating阶段：结果验证

**验证规则**:
1. 所有任务状态为`completed`
2. 关键任务结果非空（如搜索至少返回1条）
3. 无工具调用错误

**失败处理**:
- 验证失败 → `REFLECTING`状态
- 反思后重新规划或终止

---

## 五、瞭望采集增强

### 5.1 多层Selector回退

**文件**: `app/models/watchtower_scraper.py`（重构）

**三层回退策略**:

**Layer 1**: 标准selector（适配当前网站版本）
```python
selectors = {
    "title": ["h3 a", ".t a", "a.c-title"],
    "snippet": [".c-font-normal", ".c-abstract"],
    "source": [".c-color-gray", ".c-author"],
}
```

**Layer 2**: 通用模式（语义化标签）
```python
containers = soup.select("article, .news-item, div[class*='result']")
```

**Layer 3**: 兜底策略（提取所有链接）
```python
all_links = soup.select("a[href]")
filtered = [link for link in all_links if len(link.text) > 10]
```

### 5.2 反爬策略增强

**User-Agent池**: 4种主流浏览器UA随机切换

**浏览器指纹模拟**:
```python
headers = {
    "Accept": "text/html,application/xhtml+xml,...",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    ...
}
```

**重试机制**: 3次指数退避（1s → 2s → 4s）

### 5.3 采集日志系统

**新增表**: `watchtower_logs`

**记录内容**:
- source_id, url, status（success/partial/failed）
- items_count, error_message, response_time
- created_at

**用途**:
- 诊断采集失败原因
- 统计各源成功率
- 性能监控（response_time）

---

## 六、深度采集并发化

### 6.1 当前问题

**现状**:
```python
for item_id in item_ids:
    await _process_one(item_id, crawler)  # 串行
```

**耗时**: 10条 × 15秒/条 = 150秒

### 6.2 解决方案

**并发执行**:
```python
results = await executor.run_concurrent([
    _process_one(item_id, crawler) for item_id in item_ids
])
```

**耗时**: 10条 ÷ 5并发 × 15秒 = 30秒（提速5倍）

### 6.3 资源池管理

**crawl4ai实例复用**:
```python
async with AsyncWebCrawler(verbose=False) as crawler:
    # 所有条目共享一个浏览器实例
    for item_id in item_ids:
        await _process_one(item_id, crawler)
```

**降级策略**: 共享实例初始化失败 → 每个任务独立创建实例

---

## 七、数据库迁移工具

### 7.1 三层迁移策略

**Layer 1: 结构迁移**（Schema Migration）
- 从SQLite导出CREATE TABLE语句
- 转换为MySQL DDL（`AUTOINCREMENT` → `AUTO_INCREMENT`, `INTEGER PRIMARY KEY` → `INT PRIMARY KEY`）
- 在MySQL中创建表结构

**Layer 2: 数据迁移**（Data Migration）
- 分批读取SQLite数据（每批1000行）
- 批量写入MySQL（`INSERT IGNORE`去重）
- 支持断点续传（按表、按offset）

**Layer 3: 热切换**（Hot Switch）
- 获取`_switch_lock`阻塞新连接（最多等待10秒）
- 切换全局`_active_db_type`变量
- 测试新连接可用性
- 释放锁，后续请求自动路由到新数据库

### 7.2 核心API

**文件**: `app/models/db_migration.py`（新增）

**API列表**:
```python
class DatabaseMigrator:
    # 导出SQLite表结构为MySQL DDL
    @staticmethod
    def export_schema_to_mysql() -> list[str]
    
    # 在MySQL中创建表结构
    @staticmethod
    def create_mysql_schema(mysql_params: dict) -> tuple[bool, str]
    
    # 迁移单表数据（分批）
    @staticmethod
    def migrate_table_data(
        table_name: str,
        mysql_params: dict,
        batch_size: int = 1000,
        progress_callback = None
    ) -> tuple[int, int]  # (成功行数, 失败行数)
    
    # 迁移所有表（异步并发）
    @staticmethod
    async def migrate_all_tables(
        mysql_params: dict,
        tables_priority: list[str] | None = None
    ) -> dict[str, tuple[int, int]]
```

**文件**: `app/models/db_switcher.py`（增强）

**API列表**:
```python
class DatabaseSwitcher:
    # 验证MySQL连接参数
    @staticmethod
    def validate_mysql_connection(params: dict) -> tuple[bool, str]
    
    # 切换到MySQL
    @staticmethod
    def switch_to_mysql(mysql_params: dict) -> tuple[bool, str]
    
    # 切换回SQLite
    @staticmethod
    def switch_to_sqlite() -> tuple[bool, str]
    
    # 获取迁移状态
    @staticmethod
    def get_migration_status() -> dict
```

### 7.3 Web管理界面

**路由**: `/admin/db-migration`

**功能**:
1. 查看当前数据库类型（SQLite/MySQL）
2. 导出表结构（下载SQL文件）
3. 执行数据迁移（显示进度条）
4. 一键切换数据库
5. 查看各表行数统计

### 7.4 初始化问题修复

**问题**: `qq_monitors.db`文件不存在，且路径配置错误

**修复**:
```python
# app/models/db.py
DB_PATH = os.environ.get(
    "DATAFINDER_DB_PATH",
    os.path.join(_project_root(), "database", "app.db"),  # 统一路径
)

def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)  # 确保目录存在
    # ... 现有初始化逻辑
```

---

## 八、并行开发计划

### 8.1 模块分工

| 模块 | 文件 | 工期 | 依赖 |
|------|------|------|------|
| 模块1: 意图路由与技能映射 | `intent_router.py`, `employee.py` | 0.5天 | 无 |
| 模块2: TaskAgent核心引擎 | `task_agent.py`, `concurrent_executor.py` | 1.5天 | 模块1 |
| 模块3: 瞭望采集增强 | `watchtower_scraper.py`, `watchtower.py` | 1天 | 无 |
| 模块4: 深度采集并发化 | `deep.py`, `deep.py` (model) | 0.5天 | 无 |
| 模块5: 数据库迁移工具 | `db_migration.py`, `db_switcher.py` | 1天 | 无 |
| 模块6: 前端集成与测试 | 对话界面、进度条、测试脚本 | 0.5天 | 所有 |

**总工期**: 4-6天（并行开发）

### 8.2 并行执行策略

**第1轮（Day 1）**: 同时开发模块1+3+5（互不依赖）
**第2轮（Day 2-3）**: 开发模块2+4（依赖模块1）
**第3轮（Day 4）**: 模块6集成 + 全量测试

### 8.3 审计检查点

**代码质量门禁**（每个模块完成后）:
```bash
uv run ruff check app/agents/task_agent.py
uv run pyright app/agents/task_agent.py
uv run pytest test/test_task_agent.py -v
```

**AI辅助审计**:
- 使用Claude Code的`/code-review`技能
- 关注点：安全漏洞、性能瓶颈、边界条件

**集成测试**:
1. 端到端场景测试
2. 并发压力测试（深度采集10条 + 50并发请求）
3. 数据库切换无损测试

---

## 九、技术决策总结

| 决策点 | 选项A | 选项B | 选项C | **最终选择** | 理由 |
|--------|-------|-------|-------|-------------|------|
| TaskAgent触发方式 | 显式前缀 | 智能判断 | 混合模式 | **A** | 用户可控，避免误触发 |
| 深度采集并发策略 | 固定并发数 | 动态调整 | 分组批次 | **B** | 自适应负载，最优性能 |
| 瞭望采集修复优先级 | selector容错 | AI辅助 | 分源修复 | **A** | 快速提升成功率，后续迭代AI |
| 数据库迁移策略 | 全量迁移 | 渐进式 | 双写模式 | **渐进式** | 降低风险，支持回滚 |

---

## 十、风险与缓解

### 10.1 风险清单

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| TaskAgent Token消耗过高 | 中 | 中 | 默认max_iterations=8，超时自动降级 |
| 并发执行导致资源耗尽 | 高 | 低 | 动态并发控制 + 资源池限制 |
| 数据库切换失败回滚不完整 | 高 | 低 | 切换前验证 + 自动回滚机制 |
| 瞭望采集selector仍失效 | 中 | 中 | 3层回退 + 日志记录失败原因 |

### 10.2 回滚方案

1. **TaskAgent回滚**: 保留agent_loop，默认不启用TaskAgent
2. **深度采集回滚**: 保留串行逻辑，通过配置开关控制
3. **数据库回滚**: `DatabaseSwitcher.switch_to_sqlite()`一键切回

---

## 十一、测试计划

### 11.1 单元测试

**覆盖率要求**: ≥80%

**重点测试模块**:
- `task_agent.py`: 状态机转换、任务分解
- `concurrent_executor.py`: 并发控制、动态调整
- `watchtower_scraper.py`: 多层selector回退
- `db_migration.py`: 数据完整性

### 11.2 集成测试

**场景1: 完整TaskAgent流程**
```
用户输入: "/task 采集并分析西华师范大学新闻"
预期: 
1. Planning阶段返回4-6个子任务
2. Executing阶段并发执行采集
3. Validating阶段验证结果非空
4. 返回结构化分析报告
```

**场景2: 深度采集并发压力测试**
```
选择50条数据 → 点击深度采集
预期:
- 系统负载 < 80%
- 完成时间 < 150秒（50条÷5并发×15秒）
- 成功率 ≥ 90%
```

**场景3: 数据库热切换**
```
SQLite（初始）→ 迁移数据 → 切换到MySQL → 正常访问 → 切回SQLite
预期:
- 全程无502错误
- 数据一致性校验通过
- 切换时间 < 5秒
```

### 11.3 性能基准

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| 瞭望采集成功率 | 30% | 80%+ |
| 深度采集10条耗时 | 150秒 | 30秒 |
| 数据库切换耗时 | 未测试 | <5秒 |
| TaskAgent平均轮次 | N/A | 2-4轮 |

---

## 十二、后续演进方向

### 12.1 短期优化（1-2周内）

1. **AI内容提取器**: 当selector失效时，用模型直接提取HTML中的新闻正文
2. **工具链（Tool Chain）**: 支持工具组合调用（如`watchtower_search` → `deep_collect`自动串联）
3. **TaskAgent计划缓存**: 相似任务复用历史分解方案

### 12.2 中期扩展（1-2月内）

1. **多Agent协作**: WatchtowerAgent自动调度 + ScraperAgent执行 + AnalyzerAgent分析
2. **长期记忆系统**: 向量数据库存储历史决策，支持经验复用
3. **自定义工具**: 用户通过UI配置Python代码片段为新工具

### 12.3 长期愿景（3-6月）

1. **完全自主Agent**: 无需用户触发，系统根据数据新鲜度自动采集
2. **多模态支持**: 图片OCR、视频字幕提取集成到瞭望系统
3. **分布式部署**: 支持多节点并行采集，水平扩展

---

## 附录A：关键代码片段

### A.1 意图路由核心逻辑

```python
# app/models/intent_router.py

TASK_TRIGGERS = {
    "/task": "启动TaskAgent",
    "/深度分析": "TaskAgent + 深度推理",
}

def route_message(user_text: str, employee_id: int | None) -> dict:
    for prefix, description in TASK_TRIGGERS.items():
        if user_text.startswith(prefix):
            return {
                "mode": "task_agent",
                "cleaned_text": user_text[len(prefix):].strip(),
                "task_config": {"max_iterations": 8}
            }
    
    if employee_id:
        employee = EmployeeRepository.get_employee_with_tools(employee_id)
        if employee and employee.get("force_task_agent"):
            return {"mode": "task_agent", ...}
    
    return {"mode": "direct", "cleaned_text": user_text}
```

### A.2 并发执行器伪代码

```python
# app/agents/concurrent_executor.py

class ConcurrentExecutor:
    def _get_optimal_concurrency(self) -> int:
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        
        if cpu < 50 and mem < 70:
            return 10
        elif cpu < 75 and mem < 85:
            return 5
        else:
            return 2
    
    async def run_concurrent(self, awaitables: list) -> list:
        concurrency = self._get_optimal_concurrency()
        semaphore = asyncio.Semaphore(concurrency)
        
        async def _bounded(coro):
            async with semaphore:
                return await coro
        
        return await asyncio.gather(*[_bounded(c) for c in awaitables])
```

---

## 附录B：数据库Schema变更

### B.1 新增表

**watchtower_logs**（采集日志）:
```sql
CREATE TABLE watchtower_logs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    keyword TEXT,
    url TEXT,
    status TEXT,  -- success/partial/failed
    items_count INTEGER DEFAULT 0,
    error_message TEXT,
    response_time INTEGER,  -- 毫秒
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(source_id) REFERENCES watchtower_sources(id) ON DELETE CASCADE
);
```

### B.2 修改字段

**digital_employees.skills**: 从`TEXT`改为支持JSON结构
```json
{
  "skill_ids": [1, 3, 5],
  "force_task_agent": false,
  "task_config": {
    "max_iterations": 8,
    "concurrency": "dynamic"
  }
}
```

---

## 结语

本设计方案通过**混合式轻量Agent架构**，在保留现有系统稳定性的前提下，引入TaskAgent、并发执行、智能采集等能力，预期将：

1. **数字员工可用性**: 0% → 100%
2. **深度采集效率**: 提升5倍（150秒 → 30秒）
3. **瞭望采集成功率**: 30% → 80%+
4. **数据库迁移**: 从不可用到完整工具链

**实施周期**: 4-6天（并行开发）
**风险等级**: 低（渐进式增强，支持回滚）

---

**Why:** 现有Agent系统功能残缺，无法满足实际业务需求

**How to apply:** 按模块分工并行开发，每个模块通过质量门禁后集成
