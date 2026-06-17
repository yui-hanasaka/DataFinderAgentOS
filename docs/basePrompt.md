# 项目基础信息 Prompt

> 本文档用于为 AI 编程助手提供项目上下文，快速理解项目结构、技术栈、开发模式与架构设计。由 AI 维护，每次大任务完成后更新。

---

## 1. 项目概览

- **项目名称**: 智能数据瞭望与智能问数系统 (DataFinderAgentOS)
- **当前版本**: v0.7（全功能 MVP）
- **项目类型**: Web 全栈单体应用
- **项目背景**: 通过 B/S 技术实现一款智能数据采集到深度采集再到数据分析与问数的综合业务系统，以大模型驱动整个业务系统的运行，是一款轻量级的智能（体）应用
- **Python 环境**: Conda 管理（Python 3.12+）

---

## 2. 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| Web 框架 | **Tornado** 6.4+ | Python 异步 Web 框架，内置模板引擎 |
| 数据库 | **SQLite3** | 零配置嵌入式数据库，通过 Python 内置 `sqlite3` 模块访问 |
| HTTP 客户端 | **httpx** | 异步 HTTP 客户端（SSE 流读取） |
| HTTP 采集 | **requests** + **BeautifulSoup4** | 网页抓取与 HTML 解析（瞭望采集） |
| PDF 导出 | **reportlab** | 对话记录导出 PDF（含中文支持） |
| 加密 | **cryptography** | API Key 加密存储（Fernet） |
| 密码安全 | **PBKDF2-SHA256** | 100,000 次迭代 + 随机 16 字节盐值 |
| 前端 CSS | **Bootstrap 5.3.8** | 响应式 UI 框架（本地 dist/） |
| 前端图标 | **Font Awesome 6.4.0** | 图标库（本地 dist/） |
| 前端组件 | **ZUI 3.0.0** | 国产前端组件库（本地 dist/） |
| 代码检查 | **ruff** | Lint + Format |
| 类型检查 | **pyright** 1.1.410+ | 严格模式，0 errors/warnings/informations |
| 测试框架 | **pytest** 9.1+ | 35 个测试用例 |

---

## 3. 目录结构

```
project/
├── app.py                          # [入口] 应用配置、路由注册、服务器启动 (:10086)
├── app/                            # [核心] MVC 业务代码包
│   ├── controllers/                # 控制层 (Handler — 路由处理器)
│   │   ├── base.py                 # 前台 BaseHandler — 认证基类
│   │   ├── auth.py                 # 前台登录/注册/登出 (LoginHandler, RegisterHandler, LogoutHandler, LandingHandler)
│   │   ├── home.py                 # 前台首页 (HomeHandler)
│   │   ├── chat.py                 # 前台 AI 对话 (ChatHome/Session/New/Send/Delete/BatchDelete/Employee/ExportHandler)
│   │   ├── ask.py                  # 前台智能问数 (AskHomeHandler, AskQueryHandler)
│   │   ├── admin.py                # 后台管理核心 (登录/角色/用户/菜单/权限 CRUD)
│   │   ├── model_engine.py         # 后台模型引擎 (CRUD + 测试 + 流式对话)
│   │   ├── employee.py             # 后台数字员工管理
│   │   ├── skill.py                # 后台技能仓库管理
│   │   ├── watchtower.py           # 后台瞭望采集源管理
│   │   ├── watchtower_collect.py   # 后台瞭望采集搜索与保存
│   │   ├── warehouse.py            # 后台数据仓库
│   │   ├── deep.py                 # 后台深度采集
│   │   ├── api_key.py              # 后台 API Key 管理
│   │   ├── session_mgr.py          # 后台会话管理 + 对话详情
│   │   ├── screen.py               # 后台智能大屏 + 数据 API
│   │   ├── settings.py             # 后台系统设置
│   │   ├── digital_twin.py         # 后台数字孪生 (场景管理)
│   │   └── permissions.py          # 后台功能管理
│   ├── models/                     # 模型层 (Repository 静态方法数据访问)
│   │   ├── db.py                   # 数据库连接 + init_db() (22 张表)
│   │   ├── user.py                 # 前台用户认证 (UserRepository)
│   │   ├── admin.py                # 后台管理认证 + 角色/菜单 CRUD (AdminRepository)
│   │   ├── chat.py                 # 对话会话/消息 CRUD (ChatRepository)
│   │   ├── model_client.py         # OpenAI 兼容 API 客户端 (chat_complete, iter_sse_chunks)
│   │   ├── model_engine.py         # AI 模型 CRUD + Token 统计 (ModelRepository)
│   │   ├── employee.py             # 数字员工 CRUD (EmployeeRepository)
│   │   ├── skill.py                # 技能 CRUD
│   │   ├── skill_dispatcher.py     # 意图识别与技能调度 (dispatch)
│   │   ├── watchtower.py           # 瞭望采集源/条目 CRUD (SourceRepository, ItemRepository)
│   │   ├── watchtower_scraper.py   # 网页抓取引擎 (WatchtowerScraper)
│   │   ├── deep.py                 # 深度采集 CRUD + 异步 LLM 摘要 (DeepRepository)
│   │   ├── sql_guard.py            # SQL 安全校验
│   │   ├── warehouse.py            # 数据仓库查询
│   │   ├── crypto.py               # 加密工具 (AES Fernet)
│   │   ├── secrets_store.py        # API Key 安全存储
│   │   ├── rate_limit.py           # 速率限制
│   │   ├── validators.py           # 输入校验
│   │   └── errors.py               # 错误码定义
│   ├── templates/                  # 视图层 (Tornado 模板引擎)
│   │   ├── admin/                  # 后台管理侧模板
│   │   │   ├── base.html           # 后台布局壳（上/左/右三区，ZUI 风格）
│   │   │   ├── login.html          # 后台登录页
│   │   │   ├── home.html           # 后台首页/仪表盘
│   │   │   ├── users.html          # 用户管理
│   │   │   ├── roles.html          # 角色管理
│   │   │   ├── menus.html          # 功能管理
│   │   │   ├── permissions.html    # 权限管理
│   │   │   ├── models.html         # 模型引擎（科技感卡片橱窗）
│   │   │   ├── model_test.html     # 模型对话测试
│   │   │   ├── employees.html      # 数字员工
│   │   │   ├── skills.html         # 技能仓库
│   │   │   ├── watchtower.html     # 瞭望采集源管理
│   │   │   ├── watchtower_collect.html  # 瞭望采集搜索（独立炫酷风格）
│   │   │   ├── warehouse.html      # 数据仓库
│   │   │   ├── deep.html           # 深度采集
│   │   │   ├── apis.html           # API Key 管理
│   │   │   ├── sessions.html       # 会话管理
│   │   │   ├── conversations.html  # 对话详情
│   │   │   ├── screen.html         # 智能大屏
│   │   │   ├── settings.html       # 系统设置
│   │   │   ├── digital_twin.html   # 数字孪生
│   │   │   └── digital_twin_scene.html  # 数字孪生场景
│   │   └── web/                    # 前台用户侧模板
│   │       ├── base.html           # 基础模板（Glassmorphism 风格，暗/亮主题）
│   │       ├── landing.html        # 落地页
│   │       ├── login.html          # 用户登录
│   │       ├── register.html       # 用户注册
│   │       ├── index.html          # 首页
│   │       ├── chat.html           # AI 对话（ChatGPT 风格，SSE 流式）
│   │       └── ask.html            # 智能问数
│   └── static/                     # 静态资源
│       ├── css/base.css            # 自定义样式
│       └── js/base.js              # 自定义脚本（主题切换、renderSafeMarkdown、escapeHtml）
├── test/                           # 测试用例 (pytest)
│   ├── test_db.py                  # 数据库建表测试
│   ├── test_chat_repo.py           # 对话仓储测试
│   ├── test_crypto.py              # 加密测试
│   ├── test_skill_dispatcher.py    # 技能调度测试
│   ├── test_sql_guard.py           # SQL 安全测试
│   ├── test_validators.py          # 校验器测试
│   └── test_watchtower_scraper.py  # 采集器测试
├── docs/                           # 项目文档
│   ├── basePrompt.md               # 本文档（AI 维护）
│   ├── codingPrompt.md             # 编码 Prompt（人+AI 维护）
│   └── requirementPrompt.md        # 需求 Prompt（AI 维护）
├── dist/                           # 第三方前端库
│   ├── bootstrap-5.3.8-dist/       # Bootstrap 5.3.8
│   ├── fontawesome-free-6.4.0-web/ # Font Awesome 6.4.0
│   └── zui-3.0.0/                  # ZUI 3.0.0
└── database/                       # SQLite 数据库文件目录（运行时自动创建）
```

---

## 4. 架构设计

### 4.1 整体架构：经典 MVC

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Templates   │ ←── │ Controllers │ ──→ │   Models    │
│  (View)      │     │ (Handler)   │     │ (Repository)│
│ Tornado      │     │ 认证 → 业务  │     │ SQLite CRUD │
│ Templates    │     │ 响应渲染     │     │ 静态方法     │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                         ┌─────▼──────┐
                                         │   SQLite    │
                                         │  (app.db)   │
                                         └────────────┘
```

### 4.2 请求生命周期

```
请求 → Tornado Application (app.py 路由匹配)
     → AdminBaseHandler / ChatBaseHandler (认证检查)
     → Handler.get/post() (参数校验 + 业务逻辑)
     → Repository.xxx() (数据库读写)
     → self.render() / self.write() (模板渲染 / JSON/AJAX)
     → 响应返回客户端
```

### 4.3 认证机制 — 双系统独立认证

**前台用户 (web)**:
- Cookie: `username` (Secure Cookie)
- Base: `ChatBaseHandler` / `AskBaseHandler`
- 流程: 注册 → 登录 → Secure Cookie → 访问聊天/问数

**后台管理员 (admin)**:
- Cookie: `admin_username` (Secure Cookie)
- Base: `AdminBaseHandler`
- 流程: 登录 → Secure Cookie → RBAC 权限检查 → 访问管理功能
- 安全: PBKDF2-SHA256 + 5次失败锁定15分钟 + IP/账户速率限制

### 4.4 RBAC 权限模型

```
admin_users ──→ admin_roles (role_id)
admin_roles ──→ admin_role_menus (role_id, menu_id)
admin_menus ──→ URL 前缀匹配授权
```

**菜单权限检查**: 支持前缀匹配 (`path == url or path.startswith(url + "/") or path.startswith(url + "?")`)

### 4.5 流式架构 (SSE)

```
ChatSendHandler.post()
  → dispatch(user_text) → 意图识别
  → skill (weather/music) → 直接返回
  → AI (default/search) →
    → employee.model_id → ModelRepository.get_model()
    → chat_complete(base_url, api_key, model_id, messages, stream=True)
    → iter_sse_chunks(resp) → yield chunk
    → self.write("data: {json}\n\n") + await self.flush()
```

---

## 5. 路由表

### 5.1 前台用户侧

| 方法 | 路由 | Handler | 需认证 | 功能 |
|------|------|---------|--------|------|
| GET | `/` | LandingHandler | 否 | 落地页 |
| GET/POST | `/login`, `/user/login` | LoginHandler | 否 | 用户登录 |
| GET/POST | `/register`, `/user/register` | RegisterHandler | 否 | 用户注册 |
| GET | `/user/logout` | LogoutHandler | 否 | 用户登出 |
| GET | `/home` | HomeHandler | 是 | 首页 |
| GET | `/chat` | ChatHomeHandler | 是 | 对话首页 |
| GET/POST | `/chat/new` | ChatNewHandler | 是 | 创建新对话 |
| GET | `/chat/session/(\d+)` | ChatSessionHandler | 是 | 查看历史对话 |
| POST | `/chat/delete/(\d+)` | ChatDeleteHandler | 是 | 删除单条对话 |
| POST | `/chat/batch-delete` | ChatBatchDeleteHandler | 是 | 批量删除对话 |
| POST | `/chat/send/(\d+)` | ChatSendHandler | 是 | 发送消息 (SSE 流式) |
| POST | `/chat/employee` | ChatEmployeeHandler | 是 | 切换数字员工 |
| GET | `/chat/export/(\d+)` | ChatExportHandler | 是 | 导出 PDF |
| GET | `/ask` | AskHomeHandler | 是 | 智能问数首页 |
| POST | `/ask/query` | AskQueryHandler | 是 | 执行问数查询 |

### 5.2 后台管理侧

| 方法 | 路由 | Handler | 功能 |
|------|------|---------|------|
| GET/POST | `/admin/login` | AdminLoginHandler | 管理员登录 |
| GET | `/admin/logout` | AdminLogoutHandler | 管理员登出 |
| GET/POST | `/admin/home` | AdminHomeHandler | 后台首页/仪表盘 |
| GET/POST | `/admin/users` | AdminUserHandler | 用户管理 CRUD |
| GET/POST | `/admin/roles` | AdminRoleHandler | 角色管理 CRUD |
| GET/POST | `/admin/menus` | AdminMenuHandler | 菜单管理 CRUD |
| GET/POST | `/admin/permissions` | AdminPermissionHandler | 功能管理 CRUD |
| GET/POST | `/admin/models` | AdminModelEngineHandler | 模型引擎 CRUD |
| GET | `/admin/models/(\d+)/test` | AdminModelTestHandler | 模型测试页 |
| POST | `/admin/models/(\d+)/chat` | AdminModelChatHandler | 模型对话 (SSE) |
| GET/POST | `/admin/employees` | AdminEmployeeHandler | 数字员工 CRUD |
| GET/POST | `/admin/skills` | AdminSkillHandler | 技能仓库 CRUD |
| GET/POST | `/admin/watchtower` | AdminWatchtowerHandler | 瞭望采集源管理 |
| GET/POST | `/admin/watchtower/collect` | WatchtowerCollectHandler | 瞭望采集搜索 |
| GET/POST | `/admin/warehouse` | AdminWarehouseHandler | 数据仓库 |
| GET/POST | `/admin/deep` | AdminDeepHandler | 深度采集 |
| GET/POST | `/admin/apis` | AdminApiKeyHandler | API Key 管理 |
| GET/POST | `/admin/sessions` | AdminSessionMgrHandler | 会话管理 |
| GET | `/admin/conversations/(\d+)` | AdminConversationDetailHandler | 对话详情 |
| GET/POST | `/admin/screen` | AdminScreenHandler | 智能大屏配置 |
| GET/POST | `/admin/settings` | AdminSettingsHandler | 系统设置 |
| GET/POST | `/admin/digital-twin` | AdminDigitalTwinHandler | 数字孪生 |
| GET/POST | `/admin/digital-twin/scenes/(\d+)` | AdminDigitalTwinSceneHandler | 数字孪生场景 |
| GET | `/api/screen/data` | ScreenDataApiHandler | 大屏数据 API |

---

## 6. 数据模型 (22 张表)

### 6.1 用户与认证

| 表名 | 说明 |
|------|------|
| `users` | 前台普通用户 (username, password_hash, salt, email, status) |
| `admin_users` | 后台管理员 (username, password_hash, salt, role_id, status, must_change_password, failed_attempts, locked_until) |
| `admin_roles` | 管理员角色 (name, description) |
| `admin_menus` | 菜单/功能项 (name, url, icon, parent_id, sort_order) |
| `admin_role_menus` | 角色-菜单关联 (role_id, menu_id) |

### 6.2 AI 模型引擎

| 表名 | 说明 |
|------|------|
| `ai_models` | AI 模型配置 (name, base_url, api_key, model_id, is_default, model_type, temperature, max_tokens, system_prompt, enable_stream, enable_thinking, status) |
| `ai_model_usage` | Token 用量统计 (model_id, prompt_tokens, completion_tokens, created_at) |

### 6.3 数字员工与技能

| 表名 | 说明 |
|------|------|
| `digital_employees` | 数字员工 (name, avatar, model_id, system_prompt, skills, status) |
| `skills` | 技能定义 (name, code, description, trigger_prefix, api_endpoint, system_prompt, status) |

### 6.4 对话系统

| 表名 | 说明 |
|------|------|
| `chat_sessions` | 对话会话 (user_id, title, employee_id) |
| `chat_messages` | 对话消息 (session_id, role, content, skill_meta) |

### 6.5 数据采集中台

| 表名 | 说明 |
|------|------|
| `watchtower_sources` | 瞭望采集源 (name, source_type, url, url_template, request_headers, config_json, fetch_interval, status) |
| `watchtower_items` | 瞭望采集条目 (source_id, title, content, url, keywords, raw_json, is_deep_collected) |
| `deep_tasks` | 深度采集任务 (name, status, progress, logs) |
| `deep_contents` | 深度采集内容 (item_id, markdown, plain_text, summary, keywords, sentiment, risk) |

### 6.6 其他业务

| 表名 | 说明 |
|------|------|
| `ask_history` | 智能问数历史 (user_id, question, sql_query, result, model_used) |
| `api_keys` | API Key 存储 (api_type, api_key, status) |
| `data_warehouse` | 数据仓库 (watchtower 数据汇总视图) |
| `sys_settings` | 系统设置 (key-value) |
| `screen_configs` | 大屏配置 |
| `screen_widgets` | 大屏组件 |
| `digital_twin_scenes` | 数字孪生场景 |
| `digital_twin_models` | 数字孪生模型 |
| `schema_migrations` | 数据库迁移记录 |

---

## 7. 开发模式与约定

### 7.1 代码组织

1. **MVC 分层**: Controller (Handler) → Model (Repository) → Template
2. **Handler 继承**: 
   - 前台需认证 → `ChatBaseHandler` (chat.py) 或 `AskBaseHandler` (ask.py)
   - 后台需认证 → `AdminBaseHandler` (admin.py)
   - 无需认证 → `tornado.web.RequestHandler`
3. **Repository 模式**: 所有数据库访问通过 `app/models/` 下对应文件的 `@staticmethod` 方法
4. **模板继承**: 
   - 后台模板 → 继承 `admin/base.html`
   - 前台模板 → 继承 `base.html` (位于 `app/templates/base.html`)

### 7.2 数据库约定

1. **连接**: `get_connection()` 返回 `sqlite3.Connection`，使用 `with` 上下文
2. **行工厂**: `row_factory = sqlite3.Row`，访问用 `row["column"]` (不能用 `.` 语法)
3. **初始化**: 应用启动时 `init_db()` 自动建表 (`CREATE TABLE IF NOT EXISTS`)
4. **类型**: `sum(int(r["count"]) for r in rows)` — Row 值需显式转换

### 7.3 安全约定

1. **密码**: PBKDF2-SHA256, 100,000 迭代, 16 字节随机盐
2. **XSRF**: 全局开启 `xsrf_cookies=True`，表单用 `{% module xsrf_form_html() %}`
3. **SSE 端点**: `check_xsrf_cookie = pass` 豁免 XSRF
4. **速率限制**: IP + 账户维度 (`rate_limit.py`)
5. **锁定机制**: 5 次失败 → 15 分钟锁定 (`admin.py`)
6. **API Key**: Fernet 对称加密存储 (`secrets_store.py`)
7. **SQL 注入**: `sql_guard.py` 校验 + 参数化查询

### 7.4 类型注解

Python 3.12+ 风格: `X | None`, `list[X]`, `dict[K, V]`, `tuple[X, Y]`

### 7.5 运行命令

```bash
uv run python app.py          # 启动服务器 :10086 (dev 模式 autoreload)
uv run pytest                 # 运行全部 35 个测试
uv run pyright                # 类型检查 (必须 0 errors, 0 warnings, 0 informations)
uv run ruff check .           # Lint (必须 0 errors)
uv run ruff format .          # 格式化 (必须 no changes)
```

### 7.6 质量门禁 (每次改动后必须执行)

```
1. uv run ruff check .        # 0 errors, 0 #noqa
2. uv run ruff format .       # no changes left
3. uv run pyright             # 0 errors, 0 warnings, 0 informations
```

---

## 8. 设计风格

- **设计理念**: 自适应浏览器用户区、响应式布局、沉浸式操作
- **后台管理**: 企业化简约专业，ZUI 组件传统布局（上/左/右三区）
- **模型引擎**: 科技感卡片橱窗，炫酷独立风格
- **瞭望采集**: 搜索引擎式独立界面，科技感玻璃态设计
- **前台对话**: ChatGPT/豆包风格，Glassmorphism 暗/亮主题切换
- **响应式**: 移动端适配，Flex/Grid 自适应

---

## 9. 第三方依赖

### Python 库 (pyproject.toml)

| 包 | 版本 | 用途 |
|------|------|------|
| tornado | >=6.4 | Web 框架 |
| httpx | >=0.27 | 异步 HTTP 客户端 (SSE 流读取) |
| requests | >=2.34.2 | 同步 HTTP 采集 (瞭望) |
| beautifulsoup4 | >=4.15.0 | HTML 解析 (瞭望 + 深度采集) |
| cryptography | >=49.0.0 | Fernet 加密 (API Key) |
| reportlab | >=4.2 | PDF 生成 (对话导出) |
| pymysql | >=1.1 | MySQL 连接 (备用) |
| ruff | >=0.15.17 | Lint + Format |
| pyright | >=1.1.410 | 类型检查 |
| pytest | >=9.1.0 | 测试框架 |

### 前端库 (本地 dist/)

| 组件 | 版本 | 用途 |
|------|------|------|
| Bootstrap | 5.3.8 | 响应式 UI 框架 |
| Font Awesome Free | 6.4.0 | 图标库 |
| ZUI | 3.0.0 | 国产前端组件库 |

---

## 10. AI 开发指导

1. **技术栈锁定**: Tornado + SQLite3 + Tornado Templates，不引入额外框架
2. **开发顺序**: Model → Controller → Template
3. **认证集成**: 后台继承 `AdminBaseHandler`，前台继承 `ChatBaseHandler`/`AskBaseHandler`
4. **模板语法**: Tornado 模板 `{% %}` 和 `{{ }}`，非 Jinja2
5. **静态文件**: `{{ static_url('path') }}` 引用
6. **注释语言**: 中文
7. **XSRF**: 需认证页面自动保护，SSE 端点手动豁免
8. **流式响应**: 使用 `text/event-stream` + `self.write("data: ...\n\n")` + `await self.flush()`
9. **异步阻塞**: 用 `IOLoop.current().run_in_executor(None, blocking_fn)` 执行同步代码
10. **文档维护**: 大任务完成后更新 `basePrompt.md` 和 `requirementPrompt.md`
