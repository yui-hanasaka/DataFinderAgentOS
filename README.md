# DataFinder AgentOS

> 智能数据瞭望与智能问数系统

## 快速开始

**环境要求：** Python 3.12+、[uv](https://docs.astral.sh/uv/)

```bash
uv sync
uv run python app.py
```

访问 [http://localhost:10086](http://localhost:10086)

默认管理员账号：`admin` / `admin888`

## 功能概览

| 模块 | 描述 |
|---|---|
| 智能对话 | SSE 流式聊天，支持数字员工人设、多会话管理 |
| 问数 | 自然语言→SQL 查询，结果表格 + ECharts 图表，CSV 导出 |
| 导出 PDF | 对话历史导出为 PDF 文档 |
| 技能增强 | @weather、@music、@西师妹、\search 技能分发 |
| 管理后台 | 用户/角色/权限/菜单/模型引擎/数字员工等管理 |
| 数智大屏 | ECharts 折线/饼图/词云全屏大屏，30 s 自刷新 |

## 用户侧

### 对话 `/chat`

选择数字员工后开始对话，支持以下技能前缀：

| 前缀 | 说明 |
|---|---|
| `@weather <城市>` | 天气查询（需在接口管理配置 OpenWeatherMap Key） |
| `@music` | 音乐功能（开发中） |
| `@西师妹 <问题>` | 校园助手人设 |
| `\search <关键词>` | 网络搜索并注入上下文 |

输入框右侧「导出 PDF」按钮可下载当前会话记录。

### 问数 `/ask`

1. 输入自然语言查询意图（如"最近30天活跃用户数"）
2. 系统生成 SQL 并执行（仅允许 SELECT）
3. 结果表格可点击"生成图表"渲染 ECharts 图表，或"导出 CSV"下载数据

## 管理后台 `/admin`

| 路径 | 功能 |
|---|---|
| `/admin/home` | 控制台 |
| `/admin/models` | 模型引擎（CRUD + 在线测试） |
| `/admin/employees` | 数字员工 |
| `/admin/skills` | 技能管理 |
| `/admin/watchtower` | 瞭望管理 |
| `/admin/warehouse` | 数据仓库 |
| `/admin/apis` | 接口管理（API Key） |
| `/admin/sessions` | 会话管理 |
| `/admin/screen` | 数智大屏 |
| `/admin/settings` | 系统设置（数据库切换） |

## 数据库切换（MySQL）

1. 「系统设置」→「数据库」，选择 MySQL 并填写连接参数
2. 点击「测试连接」验证，保存后重启服务

> 切换 MySQL 前请确保数据库已创建并手动执行建表语句（`init_db()` 当前仅适配 SQLite 语法）。

## License

MIT
