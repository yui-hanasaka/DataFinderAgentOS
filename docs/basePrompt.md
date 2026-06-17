# 项目基础信息 Prompt

> 本文档用于为 AI 编程助手提供项目上下文，快速理解项目结构、技术栈、开发模式与架构设计。

---

## 1. 项目概览

- **项目名称**: 智能数据瞭望与智能问数系统
- **当前版本**: v0.1（Tornado 框架最小验证示例）
- **项目类型**: Web 后端应用（全栈单体应用）
- **项目背景**: 通过 B/S 技术实现一款智能数据采集到深度采集再到数据分析与问数的综合业务系统，以大模型驱动整个业务系统的运行，是一款轻量级的智能（体）应用
- **Python 环境**: Conda 管理（python3）

---

## 2. 技术栈

- **核心技术栈**: Python3（Conda）+ SQLite3 + Tornado

| 层级 | 技术 | 说明 |
|------|------|------|
| Web 框架 | **Tornado** | Python 异步 Web 框架，内置模板引擎 |
| 数据库 | **SQLite3** | 零配置嵌入式数据库，通过 Python 内置 `sqlite3` 模块访问 |
| 前端 CSS | **Bootstrap 5.3.8** | 本地 `dist/` 目录下的静态文件 |
| 前端图标 | **Font Awesome 6.4.0** | 本地 `dist/` 目录下的静态文件 |
| 前端组件 | **ZUI 3.0.0** | 本地 `dist/` 目录下的静态文件 |
| 密码安全 | **PBKDF2-SHA256** | 100,000 次迭代 + 随机 16 字节盐值 |
| 测试框架 | 无（直接脚本验证） | `test/` 目录下为手动执行的 Python 脚本 |

---

## 3. 目录结构

```
project/
├── app.py                          # [入口] 应用配置、路由注册、服务器启动
├── app/                            # [核心] MVC 业务代码包
│   ├── __init__.py                 # Python 包声明
│   ├── controllers/                # 控制层 (Controller)
│   │   ├── __init__.py             # 约定说明
│   │   ├── base.py                 # BaseHandler — 认证基类
│   │   ├── auth.py                 # LoginHandler / LogoutHandler
│   │   └── home.py                 # HomeHandler（需认证）
│   ├── models/                     # 模型层 (Model)
│   │   ├── __init__.py             # 约定说明
│   │   ├── db.py                   # 数据库连接 + 建表 (SQLite)
│   │   └── User.py                 # UserRepository — 用户仓储类
│   ├── templates/                  # 视图层 (View)
│   │   ├── admin/
│   │   │   ├── login.html          # 后台登录页（独立布局）
│   │   │   ├── base.html           # 后台布局壳（上/左/右三区）
│   │   │   └── index.html          # 后台首页（继承 base.html）
│   │   └── web/
│   │       ├── base.html           # 基础模板（供继承）
│   │       ├── login.html          # 用户侧登录页
│   │       └── index.html          # 首页
│   └── static/                     # 静态资源
│       ├── bootstrap/              # Bootstrap 5.3.8（本地部署）
│       ├── fontawesome/            # Font Awesome 6.4.0（本地部署）
│       ├── zui/                    # ZUI 3.0.0（本地部署）
│       ├── css/base.css            # 自定义样式
│       └── js/base.js              # 自定义脚本
├── test/                           # 测试脚本
│   └── test1Case1.py               # 用户模型单元测试
├── docs/                           # 项目文档
│   ├── basePrompt.md               # 本文档
│   ├── treePrompt.md               # 项目树 Prompt
│   ├── codingPrompt.md             # 编码 Prompt
│   └── requirementPrompt.md        # 需求 Prompt
├── dist/                           # 第三方前端库（本地 CDN，用于后台管理侧开发）
│   ├── bootstrap-5.3.8-dist/       # Bootstrap 5.3.8 — 响应式 UI 框架
│   ├── fontawesome-free-6.4.0-web/ # Font Awesome 6.4.0 — 图标库
│   └── zui-3.0.0/                  # ZUI 3.0.0 — 国产前端组件库
├── database/                       # SQLite 数据库文件存储目录（运行时自动创建）
├── .claude/                        # Claude Code 配置
│   ├── settings.json               # 全局权限设置
│   └── settings.local.json         # 本地权限设置
└── .vscode/                        # VSCode 编辑器配置
    └── settings.json               # Python 环境 (Conda)
```

---

## 4. 架构设计

### 4.1 整体架构：经典 MVC

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Templates   │ ←── │ Controllers │ ──→ │   Models    │
│  (View)      │     │ (Handler)   │     │ (Repository)│
│ base.html    │     │ base.py     │     │ db.py       │
│ login.html   │     │ auth.py     │     │ User.py     │
│ index.html   │     │ home.py     │     │             │
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
     → Handler.get/post()  (参数校验、调用 Model)
     → Repository 方法     (数据库读写)
     → self.render()       (模板渲染)
     → 响应返回客户端
```

### 4.3 认证机制

- **方式**: Cookie-based（Secure Cookie）
- **流程**:
  1. 用户 POST 用户名/密码到 `/user/login`
  2. `LoginHandler.post()` 调用 `UserRepository.verify_user()` 验证
  3. 验证通过 → `self.set_secure_cookie("username", username)`
  4. 后续请求 → `BaseHandler.get_current_user()` 从 Cookie 读取
  5. `@tornado.web.authenticated` 装饰器保护需登录页面
- **登出**: `/user/logout` → 清除 Cookie

---

## 5. 路由表

| 方法 | 路由 | Handler | 需认证 | 功能 |
|------|------|---------|--------|------|
| GET | `/` | LoginHandler | 否 | 显示后台登录页（admin/login.html） |
| POST | `/` | LoginHandler | 否 | 处理登录请求 |
| GET | `/home` | HomeHandler | **是** | 显示后台主页（admin/index.html，上/左/右三区布局） |
| GET | `/user/login` | LoginHandler | 否 | 登录页面（GET） |
| POST | `/user/login` | LoginHandler | 否 | 登录操作（POST） |
| GET | `/user/logout` | LogoutHandler | 否 | 登出 |

---

## 6. 数据模型

### users 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 主键 |
| username | TEXT | NOT NULL, UNIQUE | 用户名 |
| password_hash | TEXT | NOT NULL | PBKDF2 密码哈希 (hex) |
| salt | TEXT | NOT NULL | 随机盐值 (hex) |
| created_at | TEXT | NOT NULL | 创建时间 (datetime('now')) |

---

## 7. 开发模式与约定

### 7.1 代码组织约定

1. **模块粒度**: 一个业务模块一个 Controller 文件（如 `auth.py`、`home.py`）
2. **基类继承**: 所有 Handler 必须继承 `BaseHandler`（位于 `controllers/base.py`）
3. **静态方法**: Repository 类使用 `@staticmethod` 方法（无状态数据访问层）
4. **模板继承**: 页面模板继承 `web/base.html`，通过 `{% block body %}` 插槽填充内容

### 7.2 安全约定

1. **密码加密**: PBKDF2-SHA256，100,000 次迭代，16 字节随机盐
2. **XSRF 防护**: 全局开启 `xsrf_cookies=True`，表单需包含 `{% module xsrf_form_html() %}`
3. **Cookie Secret**: 生产环境需替换 `demo-cookie-secret-change-me`
4. **用户输入**: 通过 `self.get_body_argument()` 获取 POST 参数

### 7.3 数据库约定

1. **连接管理**: 通过 `get_connection()` 获取连接，使用 `with` 上下文自动关闭
2. **行工厂**: `conn.row_factory = sqlite3.Row`，查询结果按列名访问
3. **初始化**: 应用启动时调用 `init_db()` 自动建表（`CREATE TABLE IF NOT EXISTS`）

### 7.4 运行配置

- **端口**: `10086`
- **调试模式**: `debug=True`, `autoreload=True`（代码变更自动重载）
- **启动**: `python app.py`

---

## 8. 第三方依赖

### Python 库

- `tornado` — Web 框架（唯一外部依赖）
- 其余均为 Python 标准库：`os`, `sqlite3`, `hashlib`, `secrets`

### 前端库（本地 `dist/` 目录，用于后台管理侧开发）

| 组件 | 版本 | 用途 |
|------|------|------|
| **ZUI** | 3.0.0 | 国产前端组件库，提供丰富的 UI 组件 |
| **Bootstrap** | 5.3.8 | 响应式 UI 框架，提供栅格布局与基础样式 |
| **Font Awesome Free** | 6.4.0 | 图标库，提供丰富的矢量图标 |

---

## 9. 已知问题与待改进

1. `auth.py` 第 16-18 行：逻辑缺陷 — `set_satus` 拼写错误 (`set_status`) 且缩进不正确，POST 登录验证流程有 bug
2. `login.html` 第 1 行：模板语法 `{ % extends %}` 空格问题
3. `index.html` 第 1 行：模板语法空格问题
4. `cookie_secret` 为硬编码演示值，生产环境需更换
5. 尚无正式测试框架（当前为手动脚本测试）
6. 尚无 ORM，所有查询为手写 SQL

---

## 10. AI 开发指导

在为本项目生成代码时，请遵循以下规则：

1. **技术栈锁定**: 使用 Tornado + SQLite3 + Tornado Templates，不引入额外框架
2. **MVC 分层**: 新功能按 Model → Controller → Template 顺序开发
3. **继承约定**: 新建 Handler 必须继承 `BaseHandler`
4. **认证集成**: 需登录页面使用 `@tornado.web.authenticated` 装饰器
5. **模板语法**: 使用 Tornado 模板语法 `{% %}` 和 `{{ }}`
6. **静态文件**: 通过 `{{ static_url('path') }}` 引用
7. **Repository 模式**: 数据库访问放在 `app/models/` 下对应文件的静态方法中
8. **注释语言**: 中文注释
