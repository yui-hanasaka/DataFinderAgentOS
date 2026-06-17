# DataFinder AgentOS 全面质量审计报告 v2

> 审计时间: 2026-06-18 | 方法: 6 并行 Agent 全量扫描 | 发现总数: **70 条**

---

## 总分

| 严重程度 | 数量 | 说明 |
|---------|------|------|
| 🔴 Critical | 4 | SQL Guard 绕过 / RBAC 路由匹配 / FA 图标缺失 / Modal 遮罩失效 |
| 🟠 High | 11 | 密码策略 / 账号锁定 / 限流持久化 / 硬编码密钥 / 异常泄露 / 输入校验 / 聊天历史暴露 / 采集管线空壳 / Bootstrap 残留 / 暗色主题 |
| 🟡 Medium | 7 | Cookie Secure / 限流 per-account / SSE 断连处理 / 异常脱敏 / URL 编码 |
| 🟢 Low | 6 | 内存泄漏 / URL 注入 / 死代码 / XSS 风险 |

---

## 🔴 Critical (4 条)

### C1. SQL Guard 绕过 — 未知表静默放行
- **文件**: `app/models/sql_guard.py:84-89`
- **问题**: 当表名既不在 `_ALLOWED_TABLES` 也不在 `_DENIED_TABLES` 时执行 `pass`，未知表静默通过。
- **修复**: 改 `pass` 为 `return False, '查询包含未授权的数据表'`；将 6 张新表加入 `_DENIED_TABLES`

### C2. RBAC 路由匹配 — 动态路由 403
- **文件**: `app/controllers/admin.py:59`
- **问题**: `prepare()` 用精确字符串匹配对比 `path` 和 `allowed_urls`。5 个含动态参数的 Handler (`models/(\d+)/test`, `models/(\d+)/chat` 等) 永远不匹配，非 super 管理员全部 403。
- **修复**: 改为前缀匹配：`path.startswith(url)` 或 `path.startswith(url + '/')`

### C3. Font Awesome 图标全部不显示
- **文件**: `app/templates/admin/base.html` + 11 个 CRUD 模板
- **问题**: 11 个模板共有 37+ 处 `fa-solid fa-*` 图标类，但 `admin/base.html` 从未加载 FA CSS。所有图标渲染为空白。
- **修复**: 在 base.html `<head>` 加 `<link rel="stylesheet" href="{{ static_url('fontawesome/fontawesome-free-6.4.0-web/css/all.min.css') }}">`；login.html 同理

### C4. CRUD Modal 背景点击无法关闭
- **文件**: `app/templates/admin/base.html`
- **问题**: `admin-edit-modal` 用 CSS `::before` 做遮罩，无法接收 JS 点击事件。10+ 个 CRUD modal 点背景不能关闭。
- **修复**: 加 delegated event listener: `document.addEventListener('click', function(e) { if (e.target.classList.contains('admin-edit-modal') && e.target.classList.contains('show')) { closeAllAdmModals(); } })`

---

## 🟠 High (11 条)

### H1. 默认密码强制轮换未实现
- **文件**: `app/controllers/admin.py`, `app/models/admin.py`
- **问题**: `must_change_password` 列已创建但从未检查。admin888 密码可永久使用。
- **修复**: `AdminLoginHandler.post()` 验证后检查 `must_change_password`，若为 1 则重定向到改密页

### H2. 管理员账号锁定未生效
- **文件**: `app/controllers/admin.py`, `app/models/admin.py`
- **问题**: `failed_login_count`/`locked_until` 列存在但从未更新。暴力破解无防护。
- **修复**: 登录失败时递增计数，≥5 次锁定 15 分钟；成功时清零

### H3. 限流器纯内存 — 重启丢失
- **文件**: `app/models/rate_limit.py`
- **问题**: defaultdict 纯内存，重启丢失；无定期清理，内存无限增长。
- **修复**: 改用 SQLite 表存储，Tornado PeriodicCallback 定期清理

### H4. 硬编码默认密码
- **文件**: `app/models/db.py:209,490`
- **问题**: admin/admin888 和 demo/demo123 硬编码。非 DEV 环境也不强制修改。
- **修复**: 首次启动生成随机 admin 密码打印到 stdout；demo 账号仅 DEV 且设随机密码

### H5. 模型引擎异常泄露到浏览器
- **文件**: `app/controllers/model_engine.py:134`
- **问题**: `f"模型调用失败：{ex}"` 把 httpx/LLM 原始异常返回前端
- **修复**: 返回通用提示，用 `log_error()` 记录详情

### H6. ChatBatchDelete 无防护的 `int()`
- **文件**: `app/controllers/chat.py:103`
- **问题**: `[int(i) for i in ids]` — 非数字 ID 导致 ValueError 500
- **修复**: 用 `validators.py` 的 `parse_int()` 或 `str.isdigit()` 过滤

### H7. AdminUserHandler 空 role_id 导致 500
- **文件**: `app/controllers/admin.py:218,230`
- **问题**: `int(self.get_body_argument("role_id", "0"))` — 空字符串时 `int("")` 抛 ValueError
- **修复**: 加 `or 0` 或用 `parse_int()`

### H8. SQL Guard 聊天历史暴露
- **文件**: `app/models/sql_guard.py`
- **问题**: `_ALLOWED_TABLES` 包含 `chat_sessions` 和 `chat_messages`，LLM 可能泄露用户对话
- **修复**: 移除这两个表；聊天历史导出应为独立 API

### H9. 瞭望采集 + 深度采集管线空壳
- **文件**: `app/controllers/watchtower_collect.py`, `app/controllers/deep.py`
- **问题**: 采集/深度采集 POST 返回 "功能开发中"，无实际抓取/解析/存储逻辑
- **修复**: 实现 HTTPS 抓取 + BeautifulSoup 解析 + ItemRepository.add_item()；深度采集集成 crawl4ai

### H10. Bootstrap 工具类未加载
- **文件**: 4 个模板 (employees/watchtower/deep/apis.html)
- **问题**: `d-flex`/`gap-2`/`text-truncate` 等 Bootstrap 类无 CSS 支持
- **修复**: 替换为 inline style 或在 base.css 中定义等价类

### H11. settings.html + conversations.html 暗色模式失效
- **文件**: `app/templates/admin/settings.html`, `app/templates/admin/conversations.html`
- **问题**: 内联 `<style>` 硬编码亮色值，无 `[data-theme="dark"]` 覆盖。暗色模式下文字不可读。
- **修复**: 删除内联 style，base.css 已有正确的亮/暗双模式样式

---

## 🟡 Medium (7 条)

### M1. XSRF Cookie 缺少 Secure
- **文件**: `app.py:140`
- **问题**: `xsrf_cookie_kwargs` 未包含 `secure=True`
- **修复**: 生产环境加 `secure: not dev`

### M2. 限流缺少 per-account 维度
- **文件**: `app/controllers/auth.py`
- **问题**: 登录限流仅基于 IP，无 per-account 限流
- **修复**: 加 `f"login_account:{username}"` 键，5 次/60s

### M3. SSE 断连处理不完整
- **文件**: `app/controllers/chat.py:239`, `app/controllers/model_engine.py:169-187`
- **问题**: 客户端断连后 `self.write()` 二次抛异常；模型引擎无 catch
- **修复**: 检查 `self.connection_closed`；catch `StreamClosedError`

### M4. ChatRepository 异常消息泄露
- **文件**: `app/models/chat.py:15`, `app/models/watchtower.py:38,50,62`
- **问题**: `return False, str(e)` 把 DB 原始异常返回前端
- **修复**: 返回通用错误，用 `log_error()` 记录

### M5. SQL Guard 仅检查显式 FROM/JOIN
- **文件**: `app/models/sql_guard.py`
- **问题**: 不检查 CTE/子查询中的表引用；正则可能被绕过
- **修复**: 集成 sqlparse 解析所有表引用

### M6. model_client.py per-request 创建 client
- **文件**: `app/models/model_client.py:29`
- **问题**: 每次请求创建新 AsyncClient，无连接池复用
- **修复**: 模块级共享 client

### M7. `_ALLOWED_TABLES` 包含 `data_warehouse`
- **文件**: `app/models/sql_guard.py:26`
- **问题**: `data_warehouse.sql_query` 列存储管理员 SQL 模板，应不可查询
- **修复**: 移除 `data_warehouse`

---

## 🟢 Low (6 条)

1. **RateLimiter 内存泄漏** — 过期 key 未清理时内存无限增长
2. **Ask 提示注入** — NL query 直接拼入 LLM prompt，可能被指令覆盖
3. **Weather API URL 未编码** — city 参数含特殊字符会生成错误 URL
4. **validators.py 死代码** — 已实现但无一 Controller 使用
5. **反向代理 secure 检测** — `_is_production()` 不检查 `X-Forwarded-Proto`
6. **Deep taskModal 缺少 `admin-edit-modal` 类** — 因此无玻璃风格

---

## 优先修复顺序

| 优先级 | 修复项 | 预计时间 |
|--------|--------|---------|
| P0 | C1 SQL Guard `pass` → reject | 5 min |
| P0 | C2 RBAC 前缀匹配 | 15 min |
| P0 | C3 加载 FA CSS | 5 min |
| P0 | C4 Modal backdrop 点击关闭 | 10 min |
| P1 | H7 空 role_id 500 fix | 5 min |
| P1 | H6 batch delete int(i) guard | 5 min |
| P1 | H5 model_engine 异常脱敏 | 5 min |
| P1 | H10 Bootstrap 工具类替换 | 20 min |
| P1 | H11 settings/conversations 暗色模式 | 15 min |
| P1 | H8 聊天历史从 allowlist 移除 | 2 min |
| P1 | M3 SSE 断连处理 | 20 min |
| P1 | M4 watchtower/chat 异常脱敏 | 10 min |
| P2 | H1 must_change_password 流 | 30 min |
| P2 | H2 账号锁定 | 20 min |
| P2 | H3 限流持久化 | 45 min |
| P2 | H4 随机 admin 密码 | 15 min |
| P2 | H9 采集管线实现 | 4h+ |

---

## 质量门基准

```bash
uv run pytest        # 32 passed
uv run ruff check .  # All checks passed
uv run ruff format . # 已格式化
uv run pyright       # 0 errors, 0 warnings, 0 informations
```
