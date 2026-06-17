# DataFinder AgentOS

> 智能数据瞭望与智能问数系统 — 大模型驱动的 Agentic 应用平台

DataFinder AgentOS 是一个面向 AI 时代的轻量级智能体操作系统，将 **Agentic 对话**、**代码沙箱执行**、**数据瞭望采集**、**自然语言问数** 和大屏可视化整合到统一的 Tornado + SQLite 架构中。

---

## 快速开始

**环境要求：** Python 3.12+、[uv](https://docs.astral.sh/uv/)

```bash
# 安装依赖
uv sync

# 启动开发服务器（自动检测 DEV 模式）
uv run python app.py
```

访问 [http://localhost:10086](http://localhost:10086)  
后台登录: [http://localhost:10086/admin/login](http://localhost:10086/admin/login)

### 环境变量

| 变量 | 说明 | 默认 |
|---|---|---|
| `DEV` | 开发模式 (`1`/`true`/`yes`) | 无 COOKIE_SECRET 时自动启用 |
| `COOKIE_SECRET` | Cookie 签名密钥（生产必须 ≥32 字符） | DEV 模式自动生成（重启 session 失效） |
| `DATAFINDER_SECRET_KEY` | Fernet 加密密钥 | DEV 模式自动生成 |
| `DATAFINDER_DB_PATH` | SQLite 数据库路径 | `database/app.db` |
| `ADMIN_INITIAL_PASSWORD` | 首次启动管理员密码 | DEV: `admin888`（需强制修改） |

**生产部署前必须设置 `COOKIE_SECRET` 和 `DATAFINDER_SECRET_KEY`。**

---

## 技术栈

| 层级 | 技术 |
|---|---|
| Web 框架 | Tornado 6.x (异步, SSE 流式) |
| 数据库 | SQLite3 (FK 强制 + 幂等迁移, 27 表) |
| HTTP 客户端 | httpx (AsyncClient, 流式 AI 调用) |
| 爬虫 | crawl4ai + BeautifulSoup4 + requests |
| 密码 | PBKDF2-SHA256 (100k 迭代) |
| 密钥加密 | cryptography (Fernet) |
| 前端 | 自研玻璃风格 (Glassmorphism), 亮/暗双主题 |
| 图表 | ECharts 5 |
| 图标 | Font Awesome 6.4.0 (本地) |
| 日志 | loguru |
| PDF | reportlab |
| 类型检查 | pyright (standard, 0e 0w 0i) |
| Lint/格式化 | ruff |
| JS/CSS Lint | @biomejs/biome, eslint |

---

## 项目结构

```
├── app.py                         # 入口: 42 条路由, HTTPServer, PeriodicCallback
├── app/
│   ├── controllers/               # Handler 层 (薄层, 调用 Repository)
│   │   ├── base.py                # BaseHandler: Cookie 安全设置
│   │   ├── admin.py               # 管理员登录/RBAC/CRUD (6 Handler)
│   │   ├── auth.py                # 用户登录/注册/登出 (4 Handler)
│   │   ├── chat.py                # SSE 流式 Agentic 对话 (9 Handler)
│   │   ├── ask.py                 # AI 问数 NL→SQL (2 Handler)
│   │   ├── model_engine.py        # 模型管理 + SSE 测试 (3 Handler)
│   │   ├── warehouse.py           # 数据仓库 (1 Handler)
│   │   ├── watchtower.py          # 瞭望源管理 (1 Handler)
│   │   ├── watchtower_collect.py  # 瞭望采集执行 (1 Handler)
│   │   ├── deep.py                # 深度采集任务 (1 Handler)
│   │   ├── screen.py              # 数智大屏 + 数据 API (2 Handler)
│   │   ├── settings.py            # 系统设置 (1 Handler)
│   │   ├── api_key.py             # 接口管理 (1 Handler)
│   │   ├── employee.py            # 数字员工 (1 Handler)
│   │   ├── skill.py               # 技能管理 (1 Handler)
│   │   ├── permissions.py         # 权限矩阵 (1 Handler)
│   │   ├── session_mgr.py         # 会话管理 (2 Handler)
│   │   ├── digital_twin.py        # 数字孪生 (2 Handler)
│   │   └── home.py                # 用户首页 (1 Handler)
│   ├── models/                    # Repository 层 (数据访问 + 工具)
│   │   ├── db.py                  # 连接工厂 + init_db() 幂等迁移
│   │   ├── crypto.py              # PBKDF2 密码哈希
│   │   ├── secrets_store.py       # Fernet 加密/解密/mask
│   │   ├── validators.py          # parse_int/float/bool, URL 校验
│   │   ├── rate_limit.py          # 令牌桶限流
│   │   ├── errors.py              # 统一日志 (loguru → stderr + 文件)
│   │   ├── sql_guard.py           # AI SQL 安全校验 (16 表拒绝 + 5 表允许)
│   │   ├── model_client.py        # 异步 OpenAI-compatible 客户端 (tools 支持)
│   │   ├── skill_dispatcher.py    # 前缀技能分发 (@weather / @西师妹 / \search)
│   │   ├── watchtower_scraper.py  # 多源采集引擎 (Baidu/RSS/HTML/API)
│   │   ├── watchtower.py          # 瞭望源/条目 Repository
│   │   ├── deep.py                # 深度采集 Repository
│   │   ├── warehouse.py           # 数据仓库 Repository
│   │   ├── chat.py                # 对话会话/消息 Repository
│   │   ├── model_engine.py        # 模型 Repository
│   │   ├── employee.py            # 数字员工 Repository
│   │   ├── skill.py               # 技能 Repository
│   │   ├── admin.py               # 管理员/RBAC Repository
│   │   ├── user.py                # 用户 Repository
│   │   └── __init__.py
│   ├── agents/                    # Agentic 核心 (7 文件)
│   │   ├── agent_loop.py          # 主 Agentic 循环 (max 8 turns)
│   │   ├── tool_registry.py       # 6 工具 OpenAI JSON Schema
│   │   ├── tool_executor.py       # 工具路由执行
│   │   ├── tool_reviewer.py       # 干净上下文 AI 安全预审
│   │   ├── code_sandbox.py        # Python 代码沙箱 (AST + subprocess)
│   │   └── watchtower_agent.py    # AI 驱动瞭望调度 (30min PeriodicCallback)
│   ├── templates/
│   │   ├── admin/                 # 后台模板 (22 页面 + base.html)
│   │   └── web/                   # 前台模板 (7 页面)
│   └── static/
│       ├── css/base.css           # 全局样式 (玻璃风格 + 亮/暗主题)
│       ├── js/base.js             # 主题切换 + 安全渲染
│       └── fontawesome/           # FA 6.4.0 本地
├── test/                          # pytest (7 文件, 35 条测试)
├── docs/                          # 文档
└── database/                      # SQLite 文件 (自动创建)
```

---

## Agentic 架构

### 对话管道

```
用户消息 → ChatSendHandler
  ├─ 前缀技能匹配 (@weather, @music, @西师妹, \search)
  ├─ Agentic Loop (agent_loop.run) ← 核心新增
  │   ├─ LLM 调用 (带 tools 参数)
  │   ├─ 收到 tool_calls → ToolReviewer 安全审查
  │   │   ├─ 通过 → ToolExecutor 执行 → 结果回灌 messages
  │   │   └─ 拒绝 → 终止本轮, 向用户说明
  │   └─ 收到纯文本 → SSE 流式输出
  └─ 保存 assistant 消息到 DB
```

### 6 个 AI 工具

| 工具 | 功能 | 审查 |
|---|---|---|
| `web_search` | DuckDuckGo 实时搜索 | ✅ LLM 审查 |
| `code_execute` | Python 沙箱执行 (AST 检查 + subprocess) | ✅ LLM 审查 |
| `watchtower_search` | 查询已采集瞭望数据 | ⚡ 跳过 |
| `warehouse_query` | 查询数据仓库分析结果 | ✅ LLM 审查 |
| `deep_collect` | 对 URL 执行 AI 深度采集 | ✅ LLM 审查 |
| `env_info` | Python 版本 / 依赖版本检查 | ⚡ 跳过 |

### 代码沙箱

- **AST 静态检查**: 拒绝 `import subprocess/socket/ctypes/multiprocessing/threading` 及 `exec()`/`eval()`/`os.system()`/`os.popen()`
- **执行**: `subprocess.run(sys.executable, [script], timeout=15, capture_output=True)`
- **输出截断**: stdout 8KB / stderr 2KB

### 工具安全审查

高风险工具 (`code_execute`, `deep_collect`, `web_search`, `warehouse_query`) 在调用前由独立 LLM 上下文审查——即使主对话被 prompt injection 污染，审查层仍保持干净。

---

## SSE 流式协议

对话端点 `/chat/send/<id>` 输出 `text/event-stream`，每行格式：`data: <json>\n\n`

| type | 含义 | 示例字段 |
|---|---|---|
| `text` | 文本内容块 (流式) | `content` |
| `tool_call` | AI 提议调用工具 | `name`, `args`, `id` |
| `tool_review` | 安全审查结果 | `name`, `approved`, `reason` |
| `tool_result` | 工具执行结果 | `name`, `result`, `id` |
| — | 流结束标记 | `data: [DONE]` |

**向后兼容**: 不含 `type` 的旧格式消息（如 `{"content": "..."}`）仍被前端识别为纯文本。

---

## 功能总览

### 前台用户 (`/` `/home` `/chat` `/ask`)

| 功能 | 路由 | 说明 |
|---|---|---|
| 落地页 | `/` | 产品介绍 |
| 登录/注册 | `/login` `/register` | Cookie-based 认证, 密码 ≥8 位 |
| 首页 | `/home` | 一言 API, 最近对话 |
| Agentic 对话 | `/chat` | SSE 流式, 工具调用卡片, Markdown 渲染 |
| 模型切换 | `/chat/model` (POST) | 会话级模型覆盖 (覆盖员工绑定) |
| 数字员工 | `/chat/employee` (POST) | 切换人设 + 系统提示词 |
| AI 问数 | `/ask` | 自然语言→SQL→表格/图表/CSV (不暴露 SQL) |
| PDF 导出 | `/chat/export/<id>` | 对话历史 PDF (中文支持) |

**技能前缀：**

| 前缀 | 功能 | 依赖 |
|---|---|---|
| `@weather <城市>` | 实时天气 | OpenWeatherMap API Key |
| `@music` | 音乐播放器 | 开发中 |
| `@西师妹 <问题>` | 校园助手 (西南师范大学) | 无 |
| `\search <关键词>` | 联网搜索 | DuckDuckGo (免费) |

没有前缀的消息直接进入 Agentic Loop，AI 可自主决定调用工具。

### 后台管理 (`/admin`)

| 模块 | 路由 | 说明 |
|---|---|---|
| 登录/登出 | `/admin/login` `/admin/logout` | 独立 admin 认证, lockout 保护 |
| 主页 | `/admin/home` | 用户/会话/模型调用统计面板 |
| 用户管理 | `/admin/users` | CRUD, 角色绑定 |
| 角色管理 | `/admin/roles` | 菜单权限联动 |
| 功能管理 | `/admin/menus` | URL 维护 |
| 权限管理 | `/admin/permissions` | 角色-菜单矩阵 |
| 模型引擎 | `/admin/models` | OpenAI 兼容接入, Token 统计, SSE 测试聊天 |
| 模型测试 | `/admin/models/<id>/test` | 模型 API 连通性测试 |
| 数字员工 | `/admin/employees` | 人设 + 模型绑定 + 系统提示词 |
| 技能管理 | `/admin/skills` | 内置/外部技能配置 |
| 瞭望管理 | `/admin/watchtower` | 采集源 CRUD (RSS/HTML/API/Baidu) |
| 瞭望采集 | `/admin/watchtower/collect` | 关键词搜索 + 结果卡片 + 保存入仓 |
| 数据仓库 | `/admin/warehouse` | 采集数据浏览/搜索/删除/触发深度采集 |
| 深度采集 | `/admin/deep` | 任务管理, URL→markdown+摘要+情感 (LLM) |
| 接口管理 | `/admin/apis` | API Key (Fernet 加密存储, masked 展示) |
| 会话管理 | `/admin/sessions` | 用户对话历史查看 |
| 会话详情 | `/admin/conversations/<id>` | 单条对话消息浏览 |
| 数智大屏 | `/admin/screen` | ECharts 实时仪表板 |
| 系统设置 | `/admin/settings` | DB 切换, MySQL 密码测试连接 |
| 数字孪生 | `/admin/digital-twin` | 场景 + 模型/资产管理 |

---

## AI 瞭望 (Watchtower)

### 采集源类型

| source_type | 引擎 | 说明 |
|---|---|---|
| `baidu_news` (默认) | BaiduNewsScraper | 百度新闻 HTML 解析, URL 模板 `{关键词}` `{分页步进}` |
| `rss` | RssScraper | RSS 2.0 / Atom 解析 (stdlib xml.etree) |
| `html` / `generic` | GenericScraper | crawl4ai AsyncWebCrawler → Markdown 链接提取 (BS4 fallback) |
| `api` | ApiScraper | JSON API, 通过 config_json 配置 data_path + key 映射 |

### AI 调度 (WatchtowerAgent)

每 30 分钟自动执行:
1. 收集所有启用源的状态统计 (条目数、深度采集比例、上次采集时间)
2. 调用默认 LLM 做出调度决策
3. 执行决策 (trigger_deep_collect, log_observation)
4. 决策记录写入 `agent_decisions` 表

---

## 安全

- **认证**: 双系统 (用户 secure cookie + 管理员 secure cookie), HttpOnly + SameSite=Lax + production Secure
- **XSRF**: 全局启用, 所有 POST 需 `X-XSRFToken` header
- **RBAC**: 超级管理员/普通管理员菜单级权限, 路由直连鉴权
- **限流**: 登录/注册/对话/问数/模型调用/深度采集端点
- **密钥加密**: 模型 API Key、外部 API Key、MySQL 密码 Fernet 加密 (`enc:v1:` 前缀)
- **SQL 安全**: AI 问数仅允许单条 SELECT, 拒绝 16 个敏感表, allowlist 5 个公共表
- **XSS 防护**: Markdown 先 escape 再渲染; 表格用 textContent 构造
- **代码沙箱**: AST 扫描拒绝危险导入 + subprocess timeout 15s
- **工具审查**: 每次高风险工具调用前, 以干净上下文请求 LLM 安全审查
- **错误脱敏**: 前端只看安全友好提示, 详细异常写入 loguru 日志

---

## 数据库

27 张表 (含 1 张 agent_decisions), 外键在每次连接时启用。核心表：

| 表 | 说明 |
|---|---|
| `users` / `admin_users` | 用户与管理 (PBKDF2, lockout, must_change_password) |
| `admin_roles` / `admin_menus` / `admin_role_menus` | RBAC |
| `chat_sessions` / `chat_messages` | 对话 |
| `ai_models` / `ai_model_usage` | 模型 + Token 统计 |
| `digital_employees` / `skills` | 数字员工 + 技能配置 |
| `watchtower_sources` / `watchtower_items` | 瞭望采集 |
| `deep_tasks` / `deep_contents` | 深度采集 (LLM 摘要+关键词+情感) |
| `ask_history` | AI 问数审计 |
| `api_keys` / `sys_settings` | 接口管理 + 系统设置 |
| `screen_configs` / `screen_widgets` | 数智大屏 |
| `digital_twin_scenes` / `digital_twin_models` | 数字孪生 |
| `agent_decisions` | Agent 调度决策日志 |

---

## 质量门

```bash
uv run ruff check .                 # lint → 0 errors
uv run ruff format .                # 格式化
uv run pyright                      # 类型检查 → 0e 0w 0i
uv run pytest                       # 测试 → 35 passed
npx @biomejs/biome check            # JS/CSS lint → 0 errors
npx eslint app/static/js/ app/templates/ --ext .html,.js  # → 0 errors
uv run python scripts/check_templates.py  # → all clear
```

### 代码约定

- Python 3.12+ 类型: `X | None`, `list[X]`, `dict[K, V]`
- 禁止 `Optional`/`List`/`Dict`/`# noqa`/`# type: ignore`
- `sqlite3.Row` 访问必须用 `row["column"]` 括号语法
- Repository 模式: Controller → Repository → SQLite
- 模板用 Tornado Template (`{% extends %}`, `{% block body %}`)
- 所有路由从 Tornado Handler 注册, 不直接操作数据库

---

## 许可证

MIT
