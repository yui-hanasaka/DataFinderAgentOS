# 前台侧栏直接模型选择器 — 设计规格

> 状态: 待审核 | 关联: [[requirementPrompt]]

---

## 1. 目标

前台 AI 对话侧栏新增**独立模型选择器**，允许用户直接切换 AI 模型引擎，不依赖数字员工绑定。

---

## 2. 核心交互规则

- **默认行为**：`session.model_id = 0` → 模型跟随员工绑定（employee.model_id），无员工时使用系统默认模型
- **手动覆盖**：用户选择模型后 `session.model_id > 0` → 使用指定模型，员工 persona 保留（system_prompt 仍来自员工）
- **切换员工**：自动重置 `model_id = 0`（跟随新员工绑定的模型）
- **模型切换**：纯 AJAX 更新，不刷新页面
- **员工切换**：保持现有 reload 行为

---

## 3. UI 设计

### 3.1 侧栏布局

```
[Logo AgentOS]                [🌙]
[员工下拉框 ▼]
 └─ 🤖 DeepSeek-V4  ▾        ← 新增模型行
[✦ 新建对话]
[▸ 对话列表]
```

### 3.2 模型行样式

- 与侧栏玻璃态风格一致：`background: rgba(20,18,48,.5)`, `border: 1px solid rgba(139,130,255,.1)`, 圆角 11px
- 字体 13px，颜色 `#a0a0d0`，hover 时变亮
- 左侧 `🤖` 图标 + 模型名；若手动覆盖，名后跟小字 `(自选)` 标记
- 右侧 `▾` 箭头
- 无会话时：显示默认模型名 + ⭐ 标记，不可点击，opacity 降低

### 3.3 模型弹出层 (Dropdown Popover)

- 绝对定位，在模型行下方弹出
- 玻璃态模糊背景：`backdrop-filter: blur(24px) saturate(150%)`, `border-radius: 11px`
- 每行一个模型：模型名 + 类型标签（文字/多模态/视觉/向量）
- 当前使用的模型打 ✓，默认模型标 ⭐
- 点击外部自动关闭
- 暗色/亮色主题完整适配

### 3.4 无会话状态

- `ChatHomeHandler` GET 时无 `current_session`，模型行显示系统默认模型（⭐），opacity 0.5，不可点击
- 创建新会话后模型行激活

---

## 4. 数据库变更

### 4.1 chat_sessions 表新增列

```sql
ALTER TABLE chat_sessions ADD COLUMN model_id INTEGER DEFAULT 0;
```

- `0` = 跟随员工绑定模型（默认）
- `>0` = 手动指定的模型 ID

### 4.2 迁移

在 `db.py::init_db()` → `_init_business_tables()` 中新增迁移 SQL（使用 `ALTER TABLE ... ADD COLUMN` 的 IF NOT EXISTS 兜底——SQLite 不支持该语法，改用 try/except）。

实现方式：新增 `_migrate_chat_sessions_model_id()` 函数，用 `PRAGMA table_info(chat_sessions)` 检测列是否存在，不存在则执行 ALTER。

---

## 5. API 设计

### 5.1 POST `/chat/model`

**描述**: 切换当前会话的模型覆盖

**认证**: 是（`ChatBaseHandler`）

**请求体**:
```json
{
  "session_id": 42,
  "model_id": 3
}
```

- `model_id = 0`：重置为跟随员工模型

**成功响应**:
```json
{"ok": true, "model_id": 3, "model_name": "DeepSeek-V4"}
```

**错误响应**:
- 400: 参数不完整
- 403: 会话不属于当前用户
- 404: 模型不存在

### 5.2 Handler 实现

新增 `ChatModelHandler(ChatBaseHandler)`，在 `chat.py` 中：
- `post()` 校验参数 → 校验会话归属 → 校验模型存在（或 model_id=0） → `ChatRepository.update_session_model(session_id, model_id)` → 返回 JSON

### 5.3 ChatRepository 新增方法

```python
@staticmethod
def update_session_model(session_id: int, model_id: int):
    """Update the model override for a chat session."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE chat_sessions SET model_id=? WHERE id=?",
            (model_id, session_id),
        )

@staticmethod
def create_session(user_id: int, employee_id: int, title: str, model_id: int = 0):
    """Create a new chat session with optional model override."""
    # 现有逻辑 + model_id 字段
```

---

## 6. ChatSendHandler 模型解析变更

当前三级 fallback：
```
employee.model_id → 默认模型
```

改为：
```
session.model_id (手动覆盖) → employee.model_id → 默认模型
```

**关键**：employee 查询**始终执行**（用于 persona/system_prompt），不论 model_id 来源。模型解析与 persona 解耦。

伪代码：
```python
# 始终查询 employee（用于 persona）
employee = None
if session["employee_id"]:
    employee = EmployeeRepository.get_employee(session["employee_id"])

# 模型三级 fallback
model_row = None
if session["model_id"]:
    model_row = ModelRepository.get_model(session["model_id"])
if not model_row and employee and employee["model_id"]:
    model_row = ModelRepository.get_model(employee["model_id"])
if not model_row:
    model_row = ModelRepository.get_default_model()

# system_prompt 始终来自 employee（persona 保留）
system_prompt = employee["system_prompt"] if employee else model_row["system_prompt"]
```

---

## 7. 模板数据变更

### 7.1 ChatHomeHandler.get() & ChatSessionHandler.get()

新增传入模板的变量：
- `models`: `list[sqlite3.Row]` — 所有 status=enabled 的模型（调用 `ModelRepository.list_all_enabled()`）
- `current_model_id`: `int` — 生效的模型 ID
- `current_model_name`: `str` — 生效的模型显示名
- `is_model_custom`: `bool` — 是否为手动覆盖

`ModelRepository` 需新增：
```python
@staticmethod
def list_all_enabled():
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, name, model_type FROM ai_models WHERE status='enabled' ORDER BY is_default DESC, id ASC"
        ).fetchall()
```

---

## 8. 前端实现

### 8.1 HTML 结构

在 `emp-select-glass` 下方插入：
```html
<div class="model-row-glass" id="modelRow" {% if not current_session %}style="pointer-events:none;opacity:.5"{% end %}>
  <span class="model-label">🤖 <span id="modelName">{{ current_model_name }}</span>{% if is_model_custom %} <small>(自选)</small>{% end %}</span>
  <span class="model-arrow">▾</span>
  <div class="model-popover" id="modelPopover" style="display:none">
    {% for m in models %}
    <div class="model-pop-item {% if m['id'] == current_model_id %}active{% end %}"
         data-id="{{ m['id'] }}" onclick="switchModel({{ m['id'] }})">
      <span>{{ m['name'] }}</span>
      <span class="model-type-tag">{{ m['model_type'] }}</span>
    </div>
    {% end %}
  </div>
</div>
```

### 8.2 JavaScript

```javascript
// 切换模型
async function switchModel(modelId) {
  if (!SESSION_ID) return;
  const popover = document.getElementById('modelPopover');
  popover.style.display = 'none';
  
  try {
    const resp = await fetch('/chat/model', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-XSRFToken': getCookie('_xsrf')},
      body: JSON.stringify({session_id: SESSION_ID, model_id: modelId})
    });
    const data = await resp.json();
    if (data.ok) {
      document.getElementById('modelName').textContent = data.model_name;
      // 更新自选标记
      const customTag = document.querySelector('.model-label small');
      if (modelId === 0 && customTag) customTag.remove();
      else if (modelId > 0 && !customTag) {
        const tag = document.createElement('small');
        tag.textContent = '(自选)';
        document.querySelector('.model-label').appendChild(tag);
      }
      // 高亮当前选中项
      document.querySelectorAll('.model-pop-item').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.id) === modelId);
      });
    }
  } catch(e) {
    console.error('切换模型失败:', e);
  }
}

// 切换员工时重置模型（通过 reload 实现，服务端重置 model_id=0）
// 点击弹出层开关
document.getElementById('modelRow').addEventListener('click', function(e) {
  if (!SESSION_ID) return;
  const popover = document.getElementById('modelPopover');
  popover.style.display = popover.style.display === 'none' ? 'block' : 'none';
  e.stopPropagation();
});

// 点击外部关闭
document.addEventListener('click', function() {
  document.getElementById('modelPopover').style.display = 'none';
});
```

### 8.3 CSS 新增

- `.model-row-glass` — 玻璃态行样式（同 `emp-select-glass` 风格）
- `.model-popover` — 绝对定位弹出层，玻璃态模糊，z-index 高于侧栏
- `.model-pop-item` — 单个模型选项，hover 高亮，active 状态
- `.model-type-tag` — 模型类型小标签
- 暗/亮主题完整适配

---

## 9. 路由注册

在 `app.py` 中新增：
```python
from app.controllers.chat import ChatModelHandler

# 在 routes 中添加:
(r"/chat/model", ChatModelHandler),
```

---

## 10. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/models/db.py` | 修改 | 新增 migration 函数 + `init_db()` 调用 |
| `app/models/chat.py` | 修改 | `update_session_model()`, `create_session` 新增 model_id 参数 |
| `app/models/model_engine.py` | 修改 | 新增 `list_all_enabled()` |
| `app/controllers/chat.py` | 修改 | 新增 `ChatModelHandler`, `ChatSendHandler` 模型解析逻辑 |
| `app/templates/web/chat.html` | 修改 | 新增模型行 HTML + CSS + JS |
| `app.py` | 修改 | 注册新路由 |

---

## 11. 自审检查

- [x] employee 与 model 查询解耦（employee 始终查，model 独立 fallback）—— 见 §6
- [x] 模型切换不刷新页面（AJAX only）—— 见 §8.2
- [x] 无会话时显示默认模型不可点击 —— 见 §3.2, §8.1
- [x] 数据库迁移（PRAGMA table_info 检测）—— 见 §4.2
- [x] 弹出层使用自定义实现（非原生 select）—— 见 §8
- [x] `ChatEmployeeHandler` 切换员工后重置 `model_id=0` —— 在 `update_session_employee()` 调用后追加 `ChatRepository.update_session_model(session_id, 0)` —— 见 §6
- [x] 暗/亮主题适配 —— 见 §3.3, §8.3
- [x] 质量门禁要求（ruff 0 / pyright 0 / pytest 35）—— 实现阶段执行
