# 开发文档

## 环境搭建

```bash
uv sync          # 安装依赖（含 dev 组）
uv run python app.py  # 启动，autoreload 已开启
```

## 工具链

### 类型检查（pyright standard）

```bash
uv run pyright
```

配置：`pyrightconfig.json`，Python 3.12+，standard 模式，不兼容旧版类型写法（使用 `X | None` 而非 `Optional[X]`，`list[X]` 而非 `List[X]`）。

### Lint / 格式化（ruff）

```bash
uv run ruff check .
uv run ruff format .
```

### JS Lint（Biome）

```bash
npx @biomejs/biome check app/static/js/
npx @biomejs/biome format --write app/static/js/
```

配置：`biome.json`，覆盖 `app/static/js/`。

### 测试（pytest）

```bash
uv run pytest          # 运行全部测试
uv run pytest -v       # 详细输出
uv run pytest test/test_db.py  # 单文件
```

测试文件位于 `test/`，使用 pytest fixture 隔离每个测试的 SQLite DB。

## 目录说明

```
app/
├── controllers/   # Tornado Handler，负责路由和请求处理
├── models/        # Repository 层，封装数据库操作
│   ├── db.py           # 连接管理、schema 初始化
│   ├── chat.py         # 会话/消息
│   ├── employee.py     # 数字员工
│   ├── skill.py        # 技能
│   ├── skill_dispatcher.py  # @/\ 技能分发逻辑
│   ├── watchtower.py   # 瞭望源/条目
│   ├── warehouse.py    # 数据仓库 SQL
│   ├── model_engine.py # AI 模型管理
│   └── model_client.py # OpenAI-compatible HTTP 调用
├── static/        # 静态资源（Bootstrap 5、ZUI、FontAwesome 6）
└── templates/
    ├── admin/     # 后台管理模板（继承 admin/base.html）
    └── web/       # 前台用户模板（继承 web/base.html → base.html）
```

## 数据库 Schema

所有表在 `app/models/db.py::init_db()` 中自动创建。主要表：

| 表 | 用途 |
|---|---|
| `users` | 前台用户 |
| `admin_users / admin_roles / admin_menus` | 后台权限体系 |
| `ai_models / ai_model_usage` | 模型引擎 |
| `chat_sessions / chat_messages` | 用户对话 |
| `digital_employees / skills` | 数字员工与技能 |
| `watchtower_sources / watchtower_items` | 瞭望采集 |
| `data_warehouse` | 问数 SQL 预置 |
| `sys_settings` | 系统 KV 配置 |

## 新增功能指引

1. **新增 Model** — 在 `app/models/` 新建 Repository 类，使用 `get_connection()` 获取连接
2. **新增路由** — 在 `app/controllers/` 继承 `AdminBaseHandler`（后台）或 `BaseHandler`（前台），在 `app.py` 注册路由
3. **新增模板** — 后台继承 `admin/base.html`，前台继承 `base.html`（`web/` 子目录下），使用 `{% block body %}...{% end %}`
4. **新增测试** — 使用 `tmp_db` / `db_with_user` fixture（见 `test/test_db.py`）隔离数据库

## 已知限制

- MySQL 切换逻辑已实现，但 `init_db()` 建表语句使用 SQLite 语法，切换 MySQL 后需手动建表
- Tornado 为单线程，长时间同步 HTTP 调用（技能、模型）会阻塞 I/O；生产环境建议改用 `asyncio` + `httpx.AsyncClient`
- `cookie_secret` 在 `app.py` 中为硬编码占位符，部署前应替换为随机值
