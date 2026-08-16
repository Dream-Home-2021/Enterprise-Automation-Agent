# State 设计问答

## 目录

- [为什么有了 LangGraph 的 State 还要自己写？](#为什么有了-langgraph-的-state-还要自己写)
- [元数据是什么意思？类型提示引用自己有什么用处？](#元数据是什么意思类型提示引用自己有什么用处)
- [default 与 default_factory 的区别](#default-与-default_factory-的区别)
- [State 是公用的，为什么还要创建 list？](#state-是公用的为什么还要创建-list)
- [model_config 是干什么？BaseModel 又在干什么？](#model_config-是干什么basemodel-又在干什么)
- [既然都允许所有类型，还要 BaseModel 吗？生产环境怎么处理公共 State？](#既然都允许所有类型还要-basemodel-吗生产环境怎么处理公共-state)
- [extra='ignore' 怎么理解](#extraignore-怎么理解)

---

## 为什么有了 LangGraph 的 State 还要自己写？

LangGraph 内置的 `MessagesState`、`AgentState` 等只提供了底层机制（如 `messages` 字段怎么累加），大概长这样：

```python
class MessagesState(TypedDict):
    messages: Annotated[list, add_messages]
```

但实际项目还需要记录：

- 哪个 Agent 刚干过活（`last_active_agent`）
- 接力棒传给谁（`next_workflow_step`）
- 任务清单（`todo_list` / `completed_tasks`）
- 各 Agent 的产物（假设/搜索/可视化/代码/报告）
- 质检返工循环（`needs_revision` / `revision_count`）

LangGraph 不会自动发明这些字段 —— 因为它不知道你的流水线长什么样。

**总结**：LangGraph 的 State 是骨架（机制），自己的 State 是血肉（业务字段）。

---

## 元数据是什么意思？类型提示引用自己有什么用处？

### 元数据（Metadata）

类型描述"是什么"，元数据描述"附加了什么额外信息"。

```python
messages: list[BaseMessage] = Field(
    default_factory=list,
    description="工作流中交换的消息序列"   # ← 元数据
)
```

常见用途：

- 自动生成 API 文档（FastAPI 读 `description` 生成 Swagger UI）
- LLM 工具调用（把字段描述拼进 prompt，让模型理解字段含义）
- 序列化 Schema（Pydantic 的 `model_json_schema()` 会带上 description）

### 类型提示引用自己

```python
from __future__ import annotations   # 让类型提示可以引用未完成的自己

class State(BaseModel):
    def with_next(self, name: str) -> "State":   # ← 引用自己
        ...
```

没有 `from __future__ import annotations` 时，Python 在类定义未完成时就要解析 `-> State`，会报 `NameError`。加上后延迟求值，把类型提示当字符串存着，等用时再解析。

实际用途：

- 方法返回自己的类型时，IDE 能推断返回值类型，提供补全和错误检查
- 链式调用时保持类型提示

---

## default 与 default_factory 的区别

两者都是"字段没被赋值时用什么值"，但传的东西不一样：

| 参数 | 传的是什么 | 适用场景 |
|---|---|---|
| `default` | 具体的值（现成对象） | 不可变类型：`int`、`str`、`None`、`bool` |
| `default_factory` | 一个函数（callable），调用后才产生值 | 可变类型：`list`、`dict`、`set` |

### 为什么不能混用？

Python 的经典坑 —— 可变默认值陷阱：

```python
# 错误写法：所有实例共享同一个列表
class Bad:
    items: list = Field(default=[])

a = Bad()
b = Bad()
a.items.append("hello")
print(b.items)   # ['hello'] —— b 也被改了

# 正确写法：每次调用都产生新列表
class Good:
    items: list = Field(default_factory=list)

a = Good()
b = Good()
a.items.append("hello")
print(b.items)   # [] —— 互不影响
```

### 在项目中的实际用法

```python
# None 是不可变值，用 default
last_active_agent: str | None = Field(default=None)

# list 是可变值，用 default_factory
messages: list[BaseMessage] = Field(default_factory=list)
```

**简单记法**：不可变用 `default=xxx`，可变用 `default_factory=构造函数名`。

---

## State 是公用的，为什么还要创建 list？

"公用"指的是所有 Agent 共用一个 State 实例，不是共用一个空列表。

```
┌─────────────────────────────────────────────────┐
│  LangGraph 管理的 State（一个实例，贯穿全流程）    │
│  ┌───────────────────────────────────────────┐  │
│  │ messages: [msg1, msg2, msg3, ...]         │  │
│  │ last_active_agent: "search_agent"         │  │
│  │ todo_list: ["任务A", "任务B"]             │  │
│  └───────────────────────────────────────────┘  │
│        ↑ 所有 Agent 读写的是同一个对象            │
└─────────────────────────────────────────────────┘
```

`default_factory=list` 的兜底场景：

- 某个节点只返回 `{"last_active_agent": "code_agent"}`，没提 `messages`
- LangGraph 合并时，`messages` 没收到值，调用 `list()` 补一个空列表
- 防止程序崩溃

**注意**：`create_initial_state` 已经显式传了 `messages`，所以初始创建时 `default_factory` 不会被触发。它是防御性编程。

---

## model_config 是干什么？BaseModel 又在干什么？

### BaseModel

Pydantic 的父类，继承后自动获得：

- **类型校验**：字段声明是 `int`，传 `"abc"` 会报错
- **序列化**：`.model_dump()` 转字典，`.model_dump_json()` 转 JSON
- **IDE 补全**：编辑器知道有哪些字段

```python
# 不用 BaseModel
class BadState:
    def __init__(self):
        self.step_count = 0
b = BadState()
b.step_count = "abc"   # ❌ 不报错，埋雷

# 用 BaseModel
class GoodState(BaseModel):
    step_count: int
g = GoodState(step_count=0)
g.step_count = "abc"   # ❌ 立刻报错
```

### model_config

给 BaseModel 贴的规则清单，控制行为。项目中开了三个开关：

| 开关 | 作用 | 为什么需要 |
|---|---|---|
| `arbitrary_types_allowed=True` | 允许字段类型用自定义类（如 `BaseMessage`） | 默认只认 `int`/`str` 等基础类型 |
| `validate_assignment=True` | 每次赋值都校验，不只是创建时 | 防止创建后偷偷改错类型 |
| `extra='ignore'` | 遇到没声明的字段静默忽略 | LangGraph 合并状态时可能带进额外字段 |

---

## 既然都允许所有类型，还要 BaseModel 吗？生产环境怎么处理公共 State？

### 澄清：没有"都允许所有类型"

三个开关是不同维度的事：

| 开关 | 控制范围 | 是否做校验 |
|---|---|---|
| `arbitrary_types_allowed` | 字段类型声明能不能用自定义类 | 不管值对不对 |
| `validate_assignment` | 赋值时值是否符合声明 | ✅ 校验 |
| `extra` | 没声明的字段让不让进 | 不管值，只决定让进还是报错 |

BaseModel 的校验一直在工作：

```python
step_count: int
state.step_count = "abc"   # ❌ 报错，不管哪个开关
```

### 生产环境三种模式

#### 模式 A：单一大 State（项目现在用的）

```python
class State(BaseModel):
    messages: list
    todo_list: list
    search_artifacts: dict
    code_artifacts: dict
    # ... 所有字段放这里
```

- 简单，所有 Agent 读同一份
- 适合字段 < 20 个，Agent < 10 个

#### 模式 B：子图拆 State

```python
class MainState(BaseModel):
    messages: list
    current_task: str

class CodeAgentState(BaseModel):
    messages: list
    test_results: str
    fix_attempts: int
```

- 每个子图只看到自己需要的字段
- 适合 Agent 内部多步工作、字段不重叠

#### 模式 C：Store 分离

```python
class State(BaseModel):
    messages: list
    current_task: str

# Store 放数据库，跨会话持久化
```

- State 轻量，Store 持久化
- 适合产物量大、需要跨会话共享

### 当前项目的阶段

15 个字段、~10 个 Agent，单一大 State 就是最合理的选择。等以下信号再考虑重构：

- 字段超过 30 个
- 子图之间字段完全不重叠
- 需要持久化到数据库

---

## extra='ignore' 怎么理解

```python
class State(BaseModel):
    model_config = ConfigDict(extra='ignore')
    messages: list[BaseMessage]   # ← 只声明了这一个字段
```

```python
State(
    messages=[HumanMessage("你好")],
    agent_messages=[AIMessage("回复")],   # ← 没声明
    foo="bar"                             # ← 没声明
)
```

结果：

- `state.messages` → ✅ 正常
- `state.agent_messages` → ❌ 报错：没有这个属性
- `state.foo` → ❌ 报错：没有这个属性

**`agent_messages` 和 `foo` 直接被丢弃，不存、不报错。**

### 为什么需要？

LangGraph 合并状态时，节点返回的字典可能带进来各种内部字段。`extra='ignore'` 让 State 只认自己声明的字段，其余当看不见。

### 三种 extra 模式对比

| 模式 | 遇到没声明的字段 | 适用场景 |
|---|---|---|
| `'forbid'` | ❌ 报错 | 开发阶段，严格检查 |
| `'ignore'` | ✅ 静默丢弃 | 生产阶段，防止意外字段搞崩 |
| `'allow'` | ✅ 存起来 | 需要动态扩展字段 |

项目用 `'ignore'` 是生产环境的常见选择 —— 宽容但不乱。
