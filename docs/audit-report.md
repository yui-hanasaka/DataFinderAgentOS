# DataFinder AgentOS 项目质量审计报告

> 审计日期：2026-06-18
> 审计范围：全项目（app.py、controllers、models、templates、static）
> 版本：v0.1 基于 Tornado + SQLite3
> 审计方法：代码静态分析 + 需求交叉比对 + 架构合规检查

---

## 1. 安全审计

### 1.1 Cookie Secret —— 严重风险

**文件**: `app.py:101`
```python
cookie_secret="demo-cookie-secret-change-me"
```

硬编码的 Cookie Secret 是目前最严重的安全问题。任何能够读取此代码的人都可以伪造任意用户的 Cookie 并绕过整个认证系统。生产环境必须在环境变量中配置强密钥。

**修复建议**: 使用 `os.environ.get("COOKIE_SECRET", secrets.token_hex(32))` 并在生产环境通过环境变量注入。

### 1.2 认证系统分离 —— 整体合格，存在细微问题

**架构**: 前端用户 (`username` Cookie) 与后台管理员 (`admin_username` Cookie) 使用两套完全独立的认证体系。

- **正面**: 两套 Cookie 命名空间独立，不存在互相污染的风险。
- **正面**: `UserRepository.verify_user()` 和 `AdminRepository.verify_admin()` 各自使用 PBKDF2-SHA256 / 100,000 次迭代 / 16 字节随机盐。
- **问题**: `BaseHandler.get_current_user()` (app/controllers/base.py:6-10) 只检查 `username` Cookie。所有继承 `BaseHandler` 的 Handler（如 `HomeHandler`、`LoginHandler` 等）不会识别已登录的管理员。尽管这可能是设计意图（管理员与用户隔离），但在 `LandingHandler` 中存在冗余检查逻辑（auth.py:7-10），暗示设计者期望着陆页同时识别两种登录态，但这种"双识"逻辑并未在基类中统一。

**问题**: `auth.py:39-71` 的 `RegisterHandler` 存在但它的 `get_current_user` 继承自 `BaseHandler`，只检查 `username` Cookie。已登录用户访问注册页会被正确重定向，但逻辑依赖于 Handler 内的显式检查而非 `@authenticated` 装饰器，可能导致遗漏。

### 1.3 XSRF 覆盖 —— 不完全

**全局配置**: `app.py:103` 开启了 `xsrf_cookies=True`。

**已禁用 XSRF 的端点** (`check_xsrf_cookie = pass`):

| 文件 | 行号 | Handler | 原因 | 风险 |
|------|------|---------|------|------|
| `controllers/chat.py` | 108 | `ChatSendHandler` | SSE 流式响应 | 低 — POST body 需要 JSON 解析 |
| `controllers/model_engine.py` | 96 | `AdminModelChatHandler` | SSE 流式响应 | 低 |
| `controllers/ask.py` | 34 | `AskQueryHandler` | AJAX 问数 | 中 — 直接执行 AI 生成的 SQL |
| `controllers/screen.py` | 20 | `ScreenDataApiHandler` | GET 请求 | 极低 — 只读 GET |

**问题**: `AskQueryHandler` 禁用 XSRF 且会执行 AI 生成的 SQL 语句，虽然只允许 SELECT，但结合 XSRF 可利用性构成 CSRF -> 数据泄露的可能路径。

**已包含 XSRF 的模板**:

| 模板 | XSRF Token | 状态 |
|------|-----------|------|
| admin/login.html | Yes | OK |
| admin/base.html (退出按钮) | Yes | OK |
| web/login.html | Yes | OK |
| web/register.html | Yes | OK |
| admin/users.html | Yes | OK |
| admin/roles.html | Yes | OK |
| admin/menus.html | Yes | OK |
| admin/models.html | Yes | OK |
| admin/employees.html | Yes | OK |
| admin/skills.html | Yes | OK |
| admin/watchtower.html | Yes | OK |
| admin/warehouse.html | Yes | OK |
| admin/deep.html | Yes | OK |
| admin/apis.html | Yes | OK |
| admin/settings.html | Yes | OK |
| admin/permissions.html | Yes | OK |
| admin/sessions.html | Yes | OK |
| web/index.html | Yes | OK |

XSRF 覆盖完整度很高，所有含表单的页面均包含 `{% module xsrf_form_html() %}`。

### 1.4 SQL 注入检查 —— 存在漏洞

**安全（使用参数化查询）**:
- `admin.py` — 所有查询使用 `?` 占位符
- `chat.py` — 所有查询使用 `?` 占位符
- `model_engine.py` — 所有查询使用 `?` 占位符
- `employee.py`、`skill.py`、`warehouse.py`、`watchtower.py` — 全部参数化
- `user.py` — 参数化

**不安全（字符串拼接 / f-string）**:

| 文件 | 行号 | 问题代码 |
|------|------|---------|
| `controllers/api_key.py` | 15 | `f"SELECT COUNT(*) FROM api_keys {where}"` — `where` 变量来自 `keyword` 参数 |
| `controllers/api_key.py` | 19 | `f"SELECT * FROM api_keys {where} ORDER BY id DESC LIMIT ? OFFSET ?"` — 同上 |
| `controllers/ask.py` | 41 | `f"PRAGMA table_info({t['name']})"` — `t['name']` 来自 sqlite_master，一般安全但不符合最佳实践 |
| `models/chat.py` | 58-59 | `f"DELETE FROM chat_messages WHERE session_id IN (SELECT id FROM chat_sessions WHERE id IN ({placeholders}) AND user_id=?)"` — 使用 `?` 占位符拼接，实际安全但写法危险 |

**最严重**: `controllers/api_key.py:15,19` 两个查询虽然用参数 `params` 传递了 `LIKE` 的模糊匹配值，但 WHERE 子句本身是通过 f-string 拼接进去的。当前逻辑看是安全的（WHERE 子句内容由代码内部控制，不是用户直接输入），但这种模式容易在后期维护中引入注入漏洞。

`controllers/ask.py:41` 的 `_schema_hint()` 方法使用 f-string 拼接表名来查询 PRAGMA，表名来自 `sqlite_master` 查询结果而非用户输入，安全但写法不规范。

### 1.5 XSS 风险 —— 存在多处漏洞

**高风险 — innerHTML 用户数据注入**:

| 文件 | 行号 | 风险描述 |
|------|------|---------|
| `templates/web/ask.html` | 105-108 | `renderTable()` 中 `cols.map(c => \`<th>${c}</th>\`)` 和 `row[c]` 直接插入 HTML，列名和数据库值未经转义 |
| `templates/web/chat.html` | 524, 587 | `renderContent()` 处理后赋值 `innerHTML`，该函数只处理 markdown 标记（code/strong），不处理 HTML 标签 |
| `templates/web/index.html` | 302 | 来自第三方 API (hitokoto.cn) 的 `data.from_who` 和 `data.from` 直接注入 `innerHTML` |
| `templates/admin/model_test.html` | 130 | `box.innerHTML = '...对话已清空'` — 虽然是硬编码，但模式不良 |

**中风险 — 模板变量未转义**:
- 所有模板中 `{{ variable }}` 语法在 Tornado 默认配置下会自动 HTML 转义。未发现使用 `{% raw %}` 的情况，这很好。
- 但是 `renderContent()` 在客户端 JavaScript 中绕过了服务端转义保护，直接将服务端返回的文本作为 HTML 渲染。

**修复建议**:
1. `renderContent()` 在注入 HTML 前应先对文本做 HTML 实体转义，然后再转换 markdown 标记。
2. `ask.html` 的 `renderTable()` 应对列名和值使用 `textContent` 或 HTML 转义函数。
3. `index.html` 的 hitokoto 数据应使用 `textContent` 而非 `innerHTML`。

### 1.6 Cookie 安全

- **Secure Flag**: 未设置。`set_secure_cookie()` 只做签名验证，不设置 `Secure`、`HttpOnly`、`SameSite` 属性。
- **HttpOnly**: Tornado 的 `set_secure_cookie` 默认不设置 HttpOnly。但项目中 JS 需要读取 `_xsrf` Cookie（chat.html:483），所以不能全站设置 HttpOnly，但 `username` / `admin_username` 这两个认证 Cookie 应该设置 HttpOnly。
- **SameSite**: 未设置，默认为浏览器行为（通常为 Lax）。在 SSE 跨域场景下可能成为问题。

**建议**: 在 `app.py` 的 Application 配置中添加 `xsrf_cookie_kwargs` 和重写 `set_secure_cookie` 调用来设置 `HttpOnly`。

### 1.7 密码哈希 —— 合格

- **算法**: PBKDF2-SHA256（`hashlib.pbkdf2_hmac("sha256", ...)`）
- **迭代次数**: 100,000 次 — 符合 NIST 推荐（2023+）
- **盐值**: 16 字节随机盐（`secrets.token_bytes(16)`）
- **代码位置**: `app/models/db.py:23-25`（module-level）、`app/models/user.py:10-12`（module-level）、`app/models/admin.py:10-12`（module-level）

**问题**: `_hash_password` 函数在三个文件中重复定义（`db.py`、`user.py`、`admin.py`），签名和逻辑完全一致。违反了 DRY 原则，且存在维护风险（例如未来升级哈希参数时可能遗漏某一处）。

### 1.8 敏感数据明文存储 —— 高风险

- **API Key**: `ai_models.api_key` 字段以明文存储模型服务的 API Key（basePrompt.md 中甚至示例代码里直接包含了一个硬编码的阿里云 API Key）。
- **API Keys（接口管理）**: `api_keys.api_key` 字段同样明文存储。
- **MySQL 密码**: `sys_settings` 表中的 `mysql_password` 明文存储数据库密码。

**修复建议**: 至少应对 API Keys 和数据库密码做对称加密存储（如使用 Python 的 `cryptography` 库或环境变量注入）。

### 1.9 速率限制 —— 缺失

项目完全没有任何速率限制机制。以下端点尤其需要：

- `/login` 和 `/admin/login` — 暴力破解
- `/register` — 批量注册
- `/chat/send/(\d+)` — API 资源滥用
- `/admin/models/(\d+)/chat` — 模型 API 调用成本

### 1.10 其他安全问题

| 问题 | 位置 | 严重度 |
|------|------|--------|
| 弱密码策略 — 仅要求 >=6 位 | `auth.py:54` | 中 |
| 无账户锁定机制 | 全局 | 低 |
| 无请求大小限制 | 全局 | 低 |
| `_redirect_with_message` 将消息放入 URL 参数，可能泄露到 Referer header | `admin.py:44-45` | 极低 |
| 模型对话端点无请求大小限制（用户可发送巨大文本消耗 Token） | `chat.py:118`, `model_engine.py:99` | 中 |

---

## 2. 架构与代码质量审计

### 2.1 MVC 合规度

**声明架构**: MVC（Model-View-Controller）

**实际合规评估**:

| 层级 | 合规度 | 说明 |
|------|--------|------|
| Model | 80% | Repository 模式大部分遵守，但存在 4 处 Controller 直接操作 DB |
| View | 85% | 模板继承体系存在，但 admin 模板继承关系混乱（见下文） |
| Controller | 75% | 职责划分基本合理，但部分 Handler 包含业务逻辑（如 ChatSendHandler 的消息分发逻辑） |

**Controller 越界操作（应移至 Model）**:

| 文件 | Handler | 越界操作 |
|------|---------|---------|
| `controllers/api_key.py` | `AdminApiKeyHandler` | 全部 CRUD 操作使用裸 SQL，应使用 Repository |
| `controllers/deep.py` | `AdminDeepHandler` | 全部 CRUD 操作使用裸 SQL |
| `controllers/screen.py` | `_collect_stats()` | 统计分析逻辑直接在 controller 中 |
| `controllers/settings.py` | `AdminSettingsHandler` | `_load_settings()` 和 `_save()` 方法直接操作 DB |
| `controllers/chat.py` | `ChatSendHandler` | `_get_api_keys()` 方法直接操作 DB |

### 2.2 Repository 模式遵从度

**有 Repository 的实体**: User、Admin、Chat、Model、Skill、Employee、Warehouse、Watchtower (Source + Item)

**缺失 Repository 的实体**: ApiKey、DeepTask、SysSettings

这些实体的 CRUD 操作直接写在 Controller 中。建议创建 `ApiKeyRepository`、`DeepTaskRepository`、`SettingsRepository`。

### 2.3 Python 3.12+ 类型注解合规

**要求**: `X | None`、`list[X]`、`dict[K, V]`，不使用 `Optional`/`List`/`Dict`

**检查结果**:

- `model_engine.py:2`: `from typing import Any, overload` — 使用了 `typing.Any`，这是允许的（PEP 604 不涉及 Any）
- `skill_dispatcher.py:3`: `from typing import Any` — 同上
- 整体合规度：**95%**。所有新代码使用 `X | None` 语法。未发现使用 `Optional`/`List`/`Dict` 的旧语法。

**问题**: `model_engine.py:152-161` 定义了 `@overload` 的 `usage_summary` 方法，但 `Any` 在 `skill_dispatcher.py:9` 中 `DispatchResult = dict[str, Any]` 的使用是合理的。

### 2.4 代码重复

| 重复内容 | 出现位置 | 建议 |
|---------|---------|------|
| `_hash_password()` | `db.py:23-25`, `user.py:10-12`, `admin.py:10-12` | 提取到 `app/models/crypto.py` |
| `_page_offset()` | `admin.py:15-16`, `model_engine.py:9-10` | 提取到公共 utils |
| `_like()` | `admin.py:19-20`, `model_engine.py:13-14` | 同上 |
| SQL 构建模式（`where` + `params`） | 多个 Repository 文件 | 可考虑 Query Builder |
| `PER_PAGE = 20` | `admin.py`, `employee.py`, `skill.py`, `warehouse.py`, `watchtower.py` 等 8+ 个文件 | 统一到 `app/models/db.py` |
| `get_connection()` 的使用模式 | 几乎所有文件 | Repository 基类可封装 |

### 2.5 错误处理模式

**统一模式**: 绝大多数 Repository 方法返回 `tuple[bool, str | None]`，其中 `bool` 表示成功，`str` 表示错误消息。

**问题**:
1. `chat.py:14-16` — `create_session()` 的 `except Exception as e` 过于宽泛
2. `model_client.py:27` — `urlopen` 使用固定 60s 超时，无重试机制
3. `skill_dispatcher.py:84,98,108` — HTTP 调用（httpx）异常被捕获但只返回字符串错误消息，丢失了原始异常信息
4. `controllers/ask.py:84-85` — 非流式模型调用异常消息直接返回给前端，可能泄露内部信息
5. `controllers/chat.py:234-237` — 流式调用异常消息包含在响应中，可能泄露 API endpoint 信息

### 2.6 路由设计质量

**正面**:
- 命名清晰，职责明确（admin 路由有 `/admin/` 前缀）
- 正则分组用于 RESTful ID 提取（如 `/chat/session/(\d+)`）
- 路由表在 `app.py` 中集中管理

**问题**:
1. 两个登录入口指向同一 Handler: `/` -> `LandingHandler`, `/login` -> `LoginHandler`，但 `/user/login` 也指向 `LoginHandler` — 路由冗余
2. `RegisterHandler` 有 `/register` 和 `/user/register` 两个路由（冗余）
3. 缺少版本化的 API 路由前缀（无 `/api/v1/` 约定）
4. 前端路由与 API 路由混合在同一路由表中

### 2.7 模板继承体系 —— 混乱

**发现的继承链**:

```
app/templates/
├── web/
│   ├── base.html          ← 极简模板（仅 <html> 壳 + <div class="base">）
│   ├── landing.html        ← 独立页面（不继承任何模板）
│   ├── login.html          ← 独立页面（不继承任何模板）
│   ├── register.html       ← 独立页面（不继承任何模板）
│   ├── chat.html           ← {% extends "base.html" %}
│   ├── ask.html            ← {% extends "base.html" %}
│   └── index.html          ← {% extends "base.html" %}
│
└── admin/
    ├── base.html           ← 玻璃态侧边栏布局模板（完整 HTML 壳）
    ├── login.html          ← 独立页面（不继承任何模板）
    ├── home.html           ← {% extends "base.html" %} — 继承 web/base.html！
    ├── users.html          ← {% extends "base.html" %} — 继承 web/base.html！
    ├── roles.html          ← {% extends "base.html" %} — 继承 web/base.html！
    ├── menus.html          ← {% extends "base.html" %} — 继承 web/base.html！
    ├── models.html         ← 独立页面（但使用了 admin-* 类名）
    ├── skills.html         ← {% extends "base.html" %}
    ├── employees.html      ← {% extends "base.html" %}
    ├── watchtower.html     ← {% extends "base.html" %}
    ├── warehouse.html      ← {% extends "base.html" %}
    ├── deep.html           ← {% extends "base.html" %}
    ├── apis.html           ← {% extends "base.html" %}
    ├── permissions.html    ← {% extends "base.html" %}
    ├── sessions.html       ← {% extends "base.html" %}
    ├── settings.html       ← {% extends "base.html" %}
    ├── screen.html         ← (独立页面)
    ├── model_test.html     ← (独立页面)
    └── conversations.html  ← {% extends "base.html" %}
```

**严重问题**: 绝大多数管理后台页面扩展 `"base.html"`（即 `web/base.html`）而不是 `"admin/base.html"`。这意味着**这些后台页面没有侧边栏导航**，每个页面都是独立的裸页。

`admin/base.html` 拥有完整的侧边栏布局、暗色主题支持、Toast/Modal 系统，但实际只有它自己被少数后台页面使用。

**推测原因**: 后台 CRUD 页面（users/roles/menus 等）使用了旧的 `admin-*` CSS 类名体系，并依赖 Bootstrap 的 Modal 组件（`data-bs-toggle`、`data-bs-target`）。这些页面的完整 HTML 壳内包含了自己的页头、搜索栏、表格等。admin/base.html 的 `{% block body %}` 插槽期望内容只放入 `adm-workspace`，但旧模板渲染了完整的页面结构（包括 `admin-page-head`），导致内容溢出。

### 2.8 静态文件组织

```
app/static/
├── bootstrap/              Bootstrap 5.3.8
├── fontawesome/            Font Awesome 6.4.0
├── zui/                    ZUI 3.0.0
├── css/
│   ├── base.css            (1724 行)
│   └── admin-model.css     (577 行)
└── js/
    └── base.js             (28 行)
```

**问题**: ZUI 库在 `static/` 目录下但是模板中**完全没有引用 ZUI 的 CSS 或 JS**。Bootstrap 的 JS 文件也未被模板加载（模板中使用了 `data-bs-toggle` 等属性但没有 `<script>` 标签引用 Bootstrap JS）。Bootstrap CSS 同样未被任何模板的 `<link>` 标签引用。

这意味着依赖 Bootstrap Modal 实现弹窗的模板（users.html、roles.html 等）依赖的是 `admin/base.html` 中内联的 `admin-edit-modal` CSS（base.css:988-1028），以及 `/admin/home` 页面渲染时加载的 Bootstrap CSS？实际上这些页面从 web/base.html 继承，web/base.html 只有 `<link rel="stylesheet" href="{{ static_url('css/base.css') }}">` 这一行。所以 Bootstrap 的 CSS 和 JS **在当前架构下完全未生效**。

**后果**: 使用 `data-bs-toggle="modal"` 和 `data-bs-target="#userModal"` 的旧模板在非 `/admin/home` 路径下弹窗功能可能不工作。

---

## 3. 需求完成度 vs 需求文档对照

### 3.1 codingPrompt.md 需求对照

| 需求 | 状态 | 说明 |
|------|------|------|
| 设计风格：自适应 + 响应式 + 沉浸式 | ✅ 完成 | Glassmorphism 暗/亮双主题，CSS 变量控制 |
| 后台登录 - 响应式/自适应/企业化 | ✅ 完成 | admin/login.html — 玻璃态卡片 + 浅/暗主题 |
| 后台主页 - 上/左/右三区布局 | ✅ 完成 | admin/base.html 侧边栏 + admin/home.html 仪表盘 |
| 后台采用 ZUI 传统后台布局 | ⚠️ 偏离 | ZUI 库文件存在但模板未使用。采用自研 Glassmorphism 体系替代 |
| 角色管理 - CRUD/分页/搜索/联动菜单 | ✅ 完成 | admin/roles.html + AdminRoleHandler |
| 用户管理 - CRUD/分页/搜索/admin 不可删 | ✅ 完成 | admin/users.html + AdminUserHandler |
| 功能管理 - CRUD/分页/搜索/动态菜单 | ✅ 完成 | admin/menus.html + AdminMenuHandler |
| 新增/修改弹窗面板操作 | ⚠️ 部分 | 旧模板使用 Bootstrap Modal 兼容模式 |
| 删除/保存/更新确认提示 | ✅ 完成 | `data-confirm` 属性 + JS 确认弹窗 |
| 模型引擎 - 科技感独立风格 | ✅ 完成 | admin-model.css + tech-* 类名系统 |
| 模型引擎 - CRUD + 默认模型设置 | ✅ 完成 | AdminModelEngineHandler |
| 模型引擎 - OPENAI-API 范式配置 | ✅ 完成 | ai_models 表存储 base_url/api_key/model_id |
| 模型引擎 - Token 可视化统计 | ✅ 完成 | ModelRepository.usage_summary() |
| 模型引擎 - 分页 6条/页/三列 | ✅ 完成 | PER_PAGE=6, 3 列 CSS Grid |
| 模型引擎 - 单独对话测试 | ✅ 完成 | model_test.html + AdminModelTestHandler |
| 模型引擎 - 默认/类型/参数/系统提示 | ✅ 完成 | 模型编辑表单全覆盖 |
| 模型引擎 - SSE 流式响应（开关） | ✅ 完成 | support_stream 开关 + AdminModelChatHandler |
| 模型引擎 - Think 模式（开关） | ✅ 完成 | support_think 开关 + reasoning_content 解析 |
| 瞭望采集 - 采集源管理 CRUD | ✅ 完成 | watchtower_sources 表 + SourceRepository |
| 瞭望采集 - 搜索引擎式界面 | ❌ 未实现 | codingPrompt 任务7要求的独立搜索引擎风格采集界面未开发 |
| 瞭望采集 - 采集源开关选择 + 参考配置面板 | ❌ 未实现 | 同上 |
| 瞭望采集 - 橱窗模式列表选择 + 保存 | ❌ 未实现 | 同上 |
| 数据仓库 - 列表/删除/批量删除/查询 | ✅ 完成 | WarehouseRepository + AdminWarehouseHandler |
| 数据仓库 - AI 深度采集 | ⚠️ 占位 | deep_tasks 表和 AdminDeepHandler 存在但仅基础 CRUD |
| 深度采集 - 单条/批量 + 过程提示 + 日志 | ⚠️ 占位 | deep_tasks 有 progress/logs 字段但无实际执行逻辑 |
| 深度采集 - crawl4ai 技术栈 | ❌ 未实现 | 仅有表结构和框架代码 |
| 深度采集 - 完成状态在数据仓库中标注 | ⚠️ 部分 | watchtower_items 有 is_deep_collected 字段但未联动 |
| 用户登录 - 复用后台登录模块 | ✅ 完成 | LoginHandler 独立实现，UI 复用 admin-login-* CSS |
| 用户注册 | ✅ 完成 | RegisterHandler + register.html |
| AI 问数 - ChatGPT/豆包风格界面 | ✅ 完成 | chat.html — 苹果 iMessage 风格玻璃态 |
| AI 问数 - 技能工具 SQL 实现问数 | ✅ 完成 | AskHomeHandler + AskQueryHandler (NL->SQL) |
| AI 问数 - 不显示具体 SQL | ❌ 未实现 | AskQueryHandler 在响应中包含 `"sql": sql` 字段 |
| AI 问数 - 意图识别（天气/音乐/问数） | ✅ 完成 | skill_dispatcher.py 正则匹配前缀 |
| AI 问数 - 预留 @xxx 数字员工对话 | ✅ 完成 | employee 绑定和会话关联已实现 |
| AI 问数 - SSE 流式响应 | ✅ 完成 | ChatSendHandler text/event-stream |
| AI 问数 - 左侧模型服务切换 | ✅ 完成 | empSelect 下拉 + switchEmployee |
| AI 问数 - 左侧历史对话记录 | ✅ 完成 | session 列表 + 点击切换 |
| AI 问数 - Markdown 渲染 | ⚠️ 部分 | renderContent() 仅支持 code/strong，不支持列表/表格/链接 |

### 3.2 requirementPrompt.md 需求对照

| 需求 | 状态 | 说明 |
|------|------|------|
| 用户管理 (后台) | ✅ 完成 | CRUD + 分页 + 搜索 |
| 角色管理 (后台) | ✅ 完成 | CRUD + 分页 + 搜索 + 菜单联动 |
| 功能管理 (联动菜单) | ✅ 完成 | CRUD + 分页 + 搜索 + 父子菜单 |
| 模型引擎 | ✅ 完成 | 完全实现 |
| 技能仓库 | ✅ 完成 | CRUD + 内置技能 |
| 数字员工 | ✅ 完成 | CRUD + 模型绑定 + 技能绑定 |
| 瞭望采集 | ⚠️ 基础 | 采集源管理完成，搜索引擎界面未实现 |
| 数据仓库 | ✅ 完成 | CRUD + SQL 执行 |
| 深度采集 | ⚠️ 占位 | 框架就绪，核心采集逻辑未实现 |
| 智能问数 | ✅ 完成 | NL to SQL + ECharts 可视化 |
| 智能大屏 | ✅ 完成 | admin/screen.html + ScreenDataApiHandler |
| 数字孪生 | ❌ 未开始 | 无任何代码 |
| 普通大屏 | ❌ 未开始 | 无任何代码 |
| 自适应 + 用户权限管理 + 智能数据 + 大模型 | ✅ 完成 | 整体架构支撑 |

### 3.3 basePrompt.md 技术栈一致性检查

| 声明 | 实际 | 一致性 |
|------|------|--------|
| Python3 + SQLite3 + Tornado | ✅ | 一致 |
| Bootstrap 5.3.8（本地 dist/） | ⚠️ 偏离 | Bootstrap 文件在 static/ 但模板未加载 |
| Font Awesome 6.4.0（本地 dist/） | ⚠️ 偏离 | 模板中引用 `fa-solid` 等类名但未加载 CSS |
| ZUI 3.0.0（本地 dist/） | ❌ 未使用 | 文件存在但完全未被引用 |
| PBKDF2-SHA256 + 100K 迭代 + 16B 盐 | ✅ | 一致 |
| Websocket + SSE + TornadoTemplate | ⚠️ 部分 | SSE 已实现，WebSocket 未使用 |

---

## 4. 前端质量

### 4.1 Glassmorphism 一致性

**后管理台**（暗色/亮色双主题）:
- `admin/base.html` 使用 `.adm-*` 类名体系（玻璃态侧边栏 + 主区域）
- `admin/login.html` 使用 `.admlogin-*` 独立体系
- `admin/home.html` 使用 `.adm-*` 类名，是一致性最高的页面

**用户侧**:
- `web/chat.html` 使用 `.glass-*` 类名体系（Apple iMessage 风格）
- `web/login.html` 复用 `.admin-login-*` 类名但加入 `.user-login-*` 覆盖
- `web/register.html` 复用登录页布局，独立样式
- `web/landing.html` 使用 `.landing-*` 独立体系
- `web/ask.html` 继承 base.html，独立样式

**CSS 命名体系冲突**:

| 系统 | 用途 | 页面范围 |
|------|------|---------|
| `.adm-*` | 新玻璃态管理后台 | admin/base.html, admin/home.html |
| `.admin-*` | 旧版别名（兼容层） | users.html, roles.html, menus.html 等 |
| `.admlogin-*` | 管理员登录 | admin/login.html |
| `.glass-*` | 用户端聊天 | web/chat.html |
| `.landing-*` | 着陆页 | web/landing.html |
| `.tech-*` | 模型引擎科技主题 | admin/models.html 等 |
| `.admin-login-*` | 早期登录样式 | web/login.html 仍在使用 |
| `.user-login-*` | 用户登录覆盖 | web/login.html |
| `.user-register-*` | 用户注册 | web/register.html |

**问题**: 8 套 CSS 命名体系共存，base.css 从 1724 行代码中的 60% 用于维护这些体系之间的兼容性（特别是 `.adm-*` 和 `.admin-*` 的别名定义 + 暗色主题重复定义）。这严重增加了 CSS 维护负担。

### 4.2 Bootstrap 依赖状态

**声明**: basePrompt.md 声明使用 Bootstrap 5.3.8 + Font Awesome 6.4.0（本地）

**实际使用情况**:

1. **Bootstrap CSS**: 未在任何模板的 `<link>` 标签中加载。admin/home.html 等页面未引用。
2. **Bootstrap JS**: 未在任何模板的 `<script>` 标签中加载。
3. **Bootstrap 类名**: 多个模板仍然使用 `data-bs-toggle`、`data-bs-target`、`modal fade`、`btn-close`、`toast-container` 等 Bootstrap 类名和属性。这些功能依赖 `admin-edit-modal` 的 CSS 别名和 admin/base.html 中的内联 JavaScript 来模拟，但实际上 Bootstrap 的 JS 文件未被加载，所以 Bootstrap 的 Modal/Toast 原生功能**完全不可用**。
4. **Font Awesome 类名**: 模板中大量使用 `fa-solid fa-magnifying-glass`、`fa-solid fa-plus`、`fa-solid fa-star` 等 Font Awesome 类名，但**没有 `<link>` 标签加载 Font Awesome CSS**。这些图标不会显示。
5. **ZUI 库**: 完全未被任何模板引用。

**结论**: Bootstrap 和 Font Awesome 的本地文件虽然存在于 `app/static/` 中，但**在模板层面完全没有被加载**。项目的实际外观依赖 base.css 和 admin-model.css 两块自研样式实现。

### 4.3 移动端响应式

**检查结果**:

| 断点 | CSS 存在 | 实际页面 |
|------|---------|---------|
| `max-width: 980px` — 侧边栏折叠 | ✅ base.css:1030 | admin 页面 |
| `max-width: 620px` — 全宽单列 | ✅ base.css:1041 | admin 页面 |
| `max-width: 980px` — 登录页布局 | ✅ base.css:1048 | 登录/注册页 |
| `max-width: 1180px` — 模型网格 | ✅ admin-model.css:555 | 模型引擎页 |
| `max-width: 720px` — 模型表格 | ✅ admin-model.css:566 | 模型引擎页 |
| `max-width: 800px` — 聊天布局 | ✅ chat.html | 聊天页 |
| `max-width: 480px` — 聊天技能面板 | ✅ chat.html | 聊天页 |
| `max-width: 720px` — 着陆页 | ✅ landing.html | 着陆页 |

移动端响应式设计覆盖较完整，但需要注意 Bootstrap 未加载的情况下，其响应式工具类（如 `.d-none`、`.d-md-block` 等）也不会生效。

### 4.4 动画与交互质量

- **Glassmorphism 动画**: 使用了自定义 cubic-bezier 缓动函数（`--spring: cubic-bezier(.34,1.56,.64,1)`、`--ease-out-expo: cubic-bezier(.16,1,.3,1)`），视觉效果流畅
- **微交互**: 卡片 hover 时的 translateY 上浮 + 阴影增强
- **弹窗动画**: `admModalIn` keyframe 从 scale(.94) 到 scale(1)
- **消息动画**: `msgSlideUp` / `msgSlideRight` 入场动画
- **图标动画**: `iconFloat` 浮动、`iconPulse` 脉冲、`typingDot` 打字指示器
- **主题切换**: data-theme 属性切换 + localStorage 持久化 + 防 FOUC 的内联脚本

质量评级: **良好**。动画自然流畅，没有发现明显的闪烁或卡顿问题。

### 4.5 主题系统完整性

**实现方式**: `data-theme="light|dark"` 属性 + CSS 属性选择器 `[data-theme="dark"]`

**覆盖的页面**: landing、login (admin+user)、register、chat、admin (all pages via base.css)

**主题切换**: base.js 提供 `toggleTheme()` 函数，与 localStorage 同步。每个页面启动时执行内联脚本防止 FOUC。

**主题图标**: `initThemeIcon()` 更新图标（🌙/☀）和 title 属性。

**问题**: 
1. 暗色/亮色主题的 background 渐变硬编码在多个内联 `<style>` 标签中（login.html、register.html、landing.html），而非统一通过 CSS 变量控制
2. 用户端页面（chat.html 等）的主题切换按钮 CSS 类名不统一（`login-theme-btn`、`register-theme-btn`、`chat-theme-btn` 等）

---

## 5. 数据模型审计

### 5.1 表目录

| 序号 | 表名 | 用途 | 所属模块 |
|------|------|------|---------|
| 1 | `users` | 前台用户 | 用户认证 |
| 2 | `admin_roles` | 后台角色 | 权限管理 |
| 3 | `admin_users` | 后台管理员 | 认证 |
| 4 | `admin_menus` | 菜单/功能 | 权限管理 |
| 5 | `admin_role_menus` | 角色-菜单关联 | 权限管理 |
| 6 | `ai_models` | AI 模型配置 | 模型引擎 |
| 7 | `ai_model_usage` | Token 使用记录 | 模型引擎 |
| 8 | `digital_employees` | 数字员工 | 业务模块 |
| 9 | `skills` | 技能注册 | 业务模块 |
| 10 | `chat_sessions` | 对话会话 | 用户对话 |
| 11 | `chat_messages` | 对话消息 | 用户对话 |
| 12 | `watchtower_sources` | 瞭望采集源 | 瞭望采集 |
| 13 | `watchtower_items` | 采集数据条目 | 瞭望采集 |
| 14 | `deep_tasks` | 深度采集任务 | 深度采集 |
| 15 | `api_keys` | 外部 API 密钥 | 接口管理 |
| 16 | `data_warehouse` | 数据仓库查询 | 数据仓库 |
| 17 | `sys_settings` | 系统设置 | 系统管理 |

共计 17 张表。

### 5.2 缺失的表（按需求文档应该存在但未创建）

| 需求功能 | 需要的表 | 状态 |
|---------|---------|------|
| 数字孪生 | `digital_twin_scenes`、`digital_twin_models` | ❌ 未开始 |
| 普通大屏 | `screen_configs`、`screen_widgets` | ❌ 未开始 |
| 深度采集详细内容 | `deep_content`（存储爬取后的完整文章） | ❌ 缺失，watchtower_items 只有 content TEXT 字段 |
| 用户角色关联（前台） | `user_roles`（前台用户与角色的关联） | ❌ 缺失 |
| 数据问数历史 | `ask_history` | ❌ 缺失 |

### 5.3 索引缺失

**现状**: 所有表的 PRIMARY KEY 都使用 `INTEGER PRIMARY KEY AUTOINCREMENT`，SQLite 自动为其创建索引。但除此之外**没有任何显式的二级索引**。

以下查询需要索引优化：

| 查询场景 | 需要的索引 |
|---------|-----------|
| `chat_sessions WHERE user_id=? ORDER BY updated_at DESC` | `(user_id, updated_at)` |
| `chat_messages WHERE session_id=? ORDER BY id` | `(session_id, id)` |
| `watchtower_items WHERE source_id=? ORDER BY id DESC` | `(source_id, id)` |
| `ai_model_usage WHERE model_id=?` | `(model_id)` |
| `admin_users WHERE username=?` | UNIQUE 已覆盖 |
| 所有模糊搜索的 `LIKE` 字段 | SQLite FTS 或至少为高频搜索字段建索引 |

### 5.4 外键约束执行

SQLite **默认不强制外键约束**（需要 `PRAGMA foreign_keys = ON`）。

**db.py 中的 get_connection()** (line 16-20) 创建连接后**未执行** `PRAGMA foreign_keys = ON`。

**后果**: 以下引用完整性约束不会被 SQLite 强制检查：
- `chat_messages.session_id -> chat_sessions.id`
- `watchtower_items.source_id -> watchtower_sources.id`
- `admin_users.role_id -> admin_roles.id`
- `admin_role_menus.role_id -> admin_roles.id`
- `admin_role_menus.menu_id -> admin_menus.id`
- `ai_model_usage.model_id -> ai_models.id`

这意味着可以插入引用了不存在 ID 的记录，也可以删除被引用的父记录而不清理子记录（Repository 层有手动清理，但数据库层不保证）。

**修复**: `get_connection()` 中添加 `conn.execute("PRAGMA foreign_keys = ON")`。

---

## 6. 已知 Bug 与问题清单

### 6.1 严重 Bug

| # | 文件:行号 | 问题描述 | 影响 |
|---|----------|---------|------|
| B1 | `app/models/db.py:18` | `get_connection()` 未执行 `PRAGMA foreign_keys = ON` | 外键约束完全失效 |
| B2 | `app/templates/admin/users.html:1` | 管理后台 CRUD 页面继承 `"base.html"` 而非 `"admin/base.html"` | 后台管理页面**没有侧边栏导航**、没有玻璃态外壳、没有主题切换功能、没有 Toast/Modal 系统 |
| B3 | `app.py:101` | `cookie_secret` 硬编码为演示值 | 认证 Cookie 可被伪造 |
| B4 | `app/templates/web/ask.html:105-108` | `renderTable()` 中列名和数据库值通过 `innerHTML` 直接注入，完全未转义 | 存储型 XSS（若数据库中存在恶意数据） |
| B5 | `app/templates/web/chat.html:524,587` | `renderContent()` 将服务端返回文本直接作为 HTML 渲染 | 反射型/存储型 XSS — AI 模型可能输出恶意 HTML |

### 6.2 中等 Bug

| # | 文件:行号 | 问题描述 |
|---|----------|---------|
| B6 | `app/controllers/ask.py:41` | `f"PRAGMA table_info({t['name']})"` — 虽然表名来自 sqlite_master 查询，但 f-string 拼接表名是不良实践 |
| B7 | `app/templates/web/index.html:302` | 第三方 API (hitokoto.cn) 返回数据通过 `innerHTML` 注入 — 外部数据 XSS |
| B8 | `app/controllers/chat.py:138-139` | `session["title"]` 为空字符串或 "新对话" 时才更新标题 — 如果标题是纯空格字符串则永远不会更新 |
| B9 | `app/models/chat.py:53-66` | `delete_sessions()` 的 IN 子句使用 f-string 拼接 `?` 占位符 — 虽然安全但写法脆弱 |
| B10 | `app/models/model_client.py:27` | `chat_complete()` 使用同步 `urllib.request.urlopen` 在 async handler 中调用 — 会阻塞 Tornado 事件循环 |
| B11 | `app/controllers/chat.py:139` | `user_text[:20]` 直接切片可能切断 UTF-8 多字节字符（如 emoji 或中文标点） |
| B12 | `app/controllers/model_engine.py:143-153` | `_sync_response()` 使用同步 `resp.read()` — 在 async handler 中阻塞事件循环 |
| B13 | `app/controllers/ask.py:70-79` | `AskQueryHandler` 的 `_sync_response` 同样使用同步 HTTP 调用 |

### 6.3 轻微 Bug

| # | 文件:行号 | 问题描述 |
|---|----------|---------|
| B14 | `app/models/db.py:31-38` | `CREATE TABLE` 语句中使用了 tab 缩进（混用 tab 和 space） |
| B15 | `app/templates/admin/base.html:7` | `<link>` 只加载了 `base.css`，未加载 Bootstrap/Font Awesome — 导致 `fa-solid` 等图标类名不渲染 |
| B16 | `app/templates/admin/users.html:7-8` | 搜索栏按钮使用 `<i class="fa-solid fa-magnifying-glass">` 但 Font Awesome CSS 未加载 |
| B17 | `app/models/db.py:137` | `update admin_roles set role_type='manager'...` — 这条 SQL 在每次启动时都执行，不必要的 UPDATE |
| B18 | `app/models/db.py:164-171` | 类似地，每次启动都更新 menu URL — 不必要的写操作 |
| B19 | `app/templates/admin/login.html:120` | placeholder 显示 `admin`/`admin888` 默认凭据 — 信息披露 |
| B20 | `app/controllers/auth.py:26-27` | `return self.render(...)` 在 `set_status(400)` 之后 — 函数签名不一致（有的 return render，有的不 return） |

### 6.4 架构不一致

| # | 问题 | 详情 |
|---|------|------|
| B21 | 两套认证类型的 Handler 公共方法分散 | `ChatBaseHandler._user_id()` (chat.py:21-26) 和 `HomeHandler` (home.py:12-14) 都有重复的用户 ID 查询逻辑 |
| B22 | SSE endpoint 没有统一的超时/清理机制 | 如果客户端断开 SSE 连接，服务端不会收到通知来取消进行中的模型调用 |
| B23 | `LandingHandler` 的路由 `/` (auth.py:5) 调用 `render("web/landing.html")`，但 landing.html 不继承任何模板 | 所有其他页面都继承 base.html，唯独 landing.html 是独立页面 |

---

## 7. 优先处理事项

### 严重（立刻修复）

| 优先级 | 事项 | 预计工时 |
|--------|------|---------|
| P0 | 修复 Cookie Secret 硬编码（app.py:101） | 5 分钟 |
| P0 | 修复 ask.html 和 chat.html 的 XSS 漏洞（innerHTML 注入） | 2 小时 |
| P0 | 修复后台 CRUD 页面模板继承问题（B2）— 统一继承 admin/base.html | 4 小时 |
| P0 | 在 get_connection() 中添加 `PRAGMA foreign_keys = ON` | 1 分钟 |
| P0 | 加载 Bootstrap CSS 和 Font Awesome CSS（或在模板中移除未实现的图标类名引用） | 30 分钟 |

### 高优先级（本周修复）

| 优先级 | 事项 | 预计工时 |
|--------|------|---------|
| P1 | 添加 API Key 和 MySQL 密码的对称加密存储 | 4 小时 |
| P1 | 为登录端点添加速率限制 | 3 小时 |
| P1 | 为 `api_key.py` 和 `deep.py` 创建独立的 Repository 类 | 3 小时 |
| P1 | 合并 `_hash_password` 到 `app/models/crypto.py` | 30 分钟 |
| P1 | 修复 `chat_complete()` 同步调用阻塞事件循环问题（使用 httpx 或 aiohttp） | 4 小时 |
| P1 | 为高频查询添加数据库索引 | 1 小时 |
| P1 | 修复 `user_text[:20]` 可能截断 UTF-8 字符的问题 | 15 分钟 |

### 中优先级（本月修复）

| 优先级 | 事项 | 预计工时 |
|--------|------|---------|
| P2 | 实现瞭望采集的搜索引擎风格界面（codingPrompt 任务7） | 8 小时 |
| P2 | 实现深度采集核心逻辑（crawl4ai 集成 + 日志系统） | 8 小时 |
| P2 | 实现 AI 问数时不暴露 SQL 语句的需求 | 1 小时 |
| P2 | 统一 CSS 命名体系（减少 8 套体系到 2-3 套） | 8 小时 |
| P2 | 清理未被引用的静态文件（ZUI/Bootstrap 冗余副本） | 30 分钟 |
| P2 | 添加统一错误处理中间件（统一 400/401/404/500 响应格式） | 2 小时 |

### 低优先级（可排期）

| 优先级 | 事项 | 预计工时 |
|--------|------|---------|
| P3 | 丰富 renderContent() 的 Markdown 支持（列表/表格/链接/图片） | 4 小时 |
| P3 | 实现数字孪生和普通大屏功能 | 16+ 小时 |
| P3 | 为 SSE 连接添加心跳和断线重连机制 | 3 小时 |
| P3 | 添加 WebSocket 支持（basePrompt.md 声明但未实现） | 8 小时 |
| P3 | 实现请求大小限制和内容安全检查 | 2 小时 |
| P3 | 添加自动化测试（pytest 单元测试 + 集成测试） | 16+ 小时 |
| P3 | 将 Font Awesome 图标类名替换为 Emoji（已在实际 UI 中大量使用 Emoji 替代） | 2 小时 |
| P3 | 清理 `db.py:_seed_admin_data()` 中每次启动都执行的重复 UPDATE 语句 | 15 分钟 |

---

## 总结

### 总体评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 安全性 | 4/10 | Cookie Secret 硬编码 + XSS 漏洞 + API Key 明文存储 + 无速率限制 |
| 架构质量 | 6/10 | MVC 基本合规，但有 5 处 Controller 越界 + 3 个缺少 Repository 的模块 |
| 代码质量 | 6/10 | 代码重复较多，错误处理不一致，Python 3.12 类型注解基本合规 |
| 需求完成度 | 6/10 | 核心功能完成约 60%，深度采集和瞭望采集界面是最大缺口 |
| 前端质量 | 5/10 | 视觉效果良好但 CSS 命名体系混乱，Bootstrap 未实际加载，模板继承关系错乱 |
| 数据模型 | 6/10 | 表结构合理但缺少索引和外键约束强制，部分表缺少关键字段 |
| 综合评分 | **5.5/10** | 功能原型可用，但存在多个安全和架构问题需要修复后才能进入生产环境 |

### 最大风险

1. **安全风险**: Cookie Secret 硬编码意味着任何可访问代码的人都能伪造认证 Cookie。
2. **用户体验风险**: 后台管理 CRUD 页面不显示侧边栏导航，用户必须在浏览器地址栏输入 URL 才能在不同管理模块间切换。
3. **功能风险**: 深度采集和瞭望采集搜索界面未实现，但它们是产品价值主张的核心卖点。
4. **性能风险**: 同步 HTTP 调用在异步 Tornado 事件循环中阻塞，高并发场景下会导致请求堆积。
