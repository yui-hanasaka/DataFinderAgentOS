# DataFinder AgentOS

> 智能数据瞭望与智能问数系统 — 以大模型驱动的轻量级智能体应用

## 快速开始

**环境要求：** Python 3.12+、[uv](https://docs.astral.sh/uv/)

```bash
# 安装依赖
uv sync

# 启动开发服务器（自动检测 DEV 模式）
uv run python app.py
```

访问 [http://localhost:10086](http://localhost:10086)

### 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `DEV` | 开发模式 (`1`/`true`/`yes`) | 无 COOKIE_SECRET 时自动启用 |
| `COOKIE_SECRET` | Cookie 签名密钥（生产必须 ≥32 字符） | DEV 模式自动生成（重启 session 失效） |
| `DATAFINDER_SECRET_KEY` | Fernet 加密密钥 | DEV 模式自动生成 |
| `DATAFINDER_DB_PATH` | SQLite 数据库路径 | `database/app.db` |
| `ADMIN_INITIAL_PASSWORD` | 首次启动管理员密码 | DEV: `admin888`（需强制修改） |

**生产部署前必须设置 `COOKIE_SECRET` 和 `DATAFINDER_SECRET_KEY`。**

---

## 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | Tornado 6.x (异步) |
| 数据库 | SQLite3 (FK 强制 + 幂等迁移) |
| HTTP 客户端 | httpx (AsyncClient) |
| 密码 | PBKDF2-SHA256 (100k 迭代) |
| 密钥加密 | cryptography (Fernet) |
| 前端 | 自研玻璃风格 (Glassmorphism), 亮/暗双主题 |
| 图表 | ECharts 5 |
| 图标 | Font Awesome 6.4.0 (本地) |
| 类型检查 | pyright (standard, 0e 0w 0i) |
| Lint/格式化 | ruff |

---

## 项目结构

```
├── app.py                    # 入口: 路由注册, HTTPServer, init_db()
├── app/
│   ├── controllers/          # Handler (薄层, 调用 Repository)
│   │   ├── base.py           # BaseHandler: set_auth_cookie/clear_auth_cookie
│   │   ├── admin.py          # 管理员登录/RBAC/用户/角色/菜单 CRUD
│   │   ├── auth.py           # 用户登录/注册/登出 + 限流
│   │   ├── chat.py           # SSE 流式对话/批量删除/PDF 导出
│   │   ├── ask.py            # AI 问数 (NL→SQL, 不暴露 SQL)
│   │   ├── home.py           # 用户首页
│   │   ├── model_engine.py   # 模型 CRUD + SSE 测试聊天
│   │   ├── warehouse.py      # 数据仓库 (采集数据 + SQL 查询库)
│   │   ├── watchtower.py     # 瞭望源管理
│   │   ├── deep.py           # 深度采集任务
│   │   ├── screen.py         # 数智大屏 + 数据 API
│   │   └── ...
│   ├── models/               # Repository + 工具类 (数据访问层)
│   │   ├── db.py             # 连接工厂 + init_db() + 幂等迁移 (26 表)
│   │   ├── crypto.py         # PBKDF2 哈希
│   │   ├── secrets_store.py  # Fernet 加密/解密/mask
│   │   ├── validators.py     # parse_int/float/bool, JSON 校验
│   │   ├── rate_limit.py     # 令牌桶限流
│   │   ├── errors.py         # 安全日志
│   │   ├── sql_guard.py      # AI SQL 校验
│   │   ├── model_client.py   # 异步 OpenAI API 客户端
│   │   ├── skill_dispatcher.py  # 异步技能分发
│   │   ├── watchtower_scraper.py # 瞭望采集执行器
│   │   └── ...
│   ├── templates/
│   │   ├── admin/            # 后台模板 (玻璃风格管理壳)
│   │   └── web/              # 前台模板
│   └── static/
│       ├── css/base.css      # 全局样式
│       ├── js/base.js        # 主题 + 安全渲染
│       └── fontawesome/      # FA 6.4.0
├── test/                     # pytest (32 条)
├── docs/                     # 文档
└── database/                 # SQLite 文件 (自动创建)
```

---

## 开发

```bash
uv run ruff check .        # lint → 0 errors
uv run ruff format .       # 格式化
uv run pyright             # 类型检查 → 0e 0w 0i
uv run pytest              # 测试 → 32 passed
```

### 代码约定

- Python 3.12+ 类型: `X | None`, `list[X]`, `dict[K, V]`
- 禁止 `Optional`/`List`/`Dict`/`# noqa`/`# type: ignore`
- `sqlite3.Row` 访问必须用 `row["column"]`
- Repository 模式: Controller → Repository → SQLite
- 模板用 Tornado Template (`{% extends %}`, `{% block body %}`)

---

## 功能总览

### 前台用户 (`/` `/chat` `/ask`)

| 功能 | 路由 | 说明 |
|------|------|------|
| 落地页 | `/` | 产品介绍 |
| 用户登录 | `/login` | Cookie-based, 限流 |
| 用户注册 | `/register` | 密码 ≥8 位 |
| 首页 | `/home` | 一言 API, 最近对话 |
| AI 对话 | `/chat` | SSE 流式, Markdown, 技能面板 |
| AI 问数 | `/ask` | 自然语言→SQL→图表/CSV |
| PDF 导出 | `/chat/export/<id>` | 对话历史 PDF |

**技能前缀：**

| 前缀 | 功能 | 依赖 |
|------|------|------|
| `@weather <城市>` | 天气 | OpenWeatherMap API Key |
| `@music` | 音乐 | 开发中 |
| `@西师妹 <问题>` | 校园助手 | 无 |
| `\search <关键词>` | 联网搜索 | DuckDuckGo (免费) |

### 后台管理 (`/admin`)

| 模块 | 路由 | 说明 |
|------|------|------|
| 后台主页 | `/admin/home` | 统计面板 |
| 用户管理 | `/admin/users` | CRUD + RBAC |
| 角色管理 | `/admin/roles` | 菜单权限联动 |
| 功能管理 | `/admin/menus` | URL 维护 |
| 权限管理 | `/admin/permissions` | 角色-菜单矩阵 |
| 模型引擎 | `/admin/models` | OpenAI 兼容接入, Token 统计, SSE 测试 |
| 数字员工 | `/admin/employees` | 人设 + 模型绑定 |
| 技能管理 | `/admin/skills` | 内置/外部技能 |
| 瞭望管理 | `/admin/watchtower` | 采集源配置 |
| 数据仓库 | `/admin/warehouse` | 采集数据 + SQL 查询库 |
| 深度采集 | `/admin/deep` | 任务管理 |
| 接口管理 | `/admin/apis` | API Key (加密存储) |
| 会话管理 | `/admin/sessions` | 用户对话查看 |
| 数智大屏 | `/admin/screen` | ECharts 实时仪表板 |
| 系统设置 | `/admin/settings` | DB 切换, MySQL 测试 |
| 数字孪生 | `/admin/digital-twin` | 开发中 |

---

## 安全

- **认证**: Tornado Secure Cookie (HttpOnly + SameSite=Lax + Secure)
- **XSRF**: 全局启用，所有 POST 需 `X-XSRFToken`
- **RBAC**: 超级管理员/普通管理员菜单级权限
- **密钥**: 模型 API Key、外部 API Key、MySQL 密码 Fernet 加密存储
- **SQL**: AI 问数仅允许 SELECT + allowlist 表 (sql_guard)
- **XSS**: Markdown 先 escape 再渲染；表格用 textContent
- **限流**: 登录/注册/对话/问数/模型调用端点

---

## 数据库

26 张表，核心表：

| 表 | 说明 |
|----|------|
| `users` / `admin_users` | 用户 |
| `admin_roles` / `admin_menus` / `admin_role_menus` | RBAC |
| `chat_sessions` / `chat_messages` | 对话 |
| `ai_models` / `ai_model_usage` | 模型 |
| `watchtower_sources` / `watchtower_items` | 采集 |
| `deep_tasks` / `deep_contents` | 深度采集 |
| `ask_history` | 问数记录 |
| `screen_configs` / `screen_widgets` | 大屏 |
| `digital_twin_scenes` / `digital_twin_models` | 数字孪生 |

外键约束在每次连接时启用 (`PRAGMA foreign_keys = ON`)，迁移为幂等执行。

---

## 许可证

MIT
