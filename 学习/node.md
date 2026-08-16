# node.py 深度导读

> 文件位置：`src/core/node.py`
> 作用：定义 LangGraph 工作流的**所有节点函数**——每个节点 = 流水线上的一个工位，接收 `State`、交给某个 Agent 处理、返回更新后的状态。

---

## 一、总览：node.py 的角色

LangGraph 把工作流建模为**有向图**。图里的节点就是这里定义的函数，边由 `core/router.py` 决定。

核心节点一览：

| 节点函数 | 职责 | 章节 |
|----------|------|------|
| `human_choice_node` | 暂停流程，问用户继续还是重新开始 | §2 |
| `create_message` | dict / 对象 → LangChain `BaseMessage` 的标准化 | §3 |
| `note_agent_node` | 读产物文件 → 压缩中间段 messages → 全状态重映射 | §4 |
| `refiner_node` | 读工作目录 `.md` → 拼起来 → Refiner 精炼 | §5 |

三个节点共涉及 Python / LangChain 的四个关键内建机制，下节专门讲。

---

## 二、四个内建机制

### 2.1 `isinstance(obj, cls)` — 类型判断（第 328、390 等行）

**词源**：`in·stance /ˈɪnstəns/`，源自拉丁语 *instantia*（由 *in-* + *stare*"站立" 演来）。编程语言里意为"obj 站在 cls 这个类里"。

#### 语义

```python
isinstance(obj, cls)  # obj 是 cls 的实例或其子类的实例 → True
```

和 `type(obj) is cls` 的区别：`isinstance` **允许子类**通过检查。

#### 在 node.py 的用途

最核心一处（[node.py:328](src/core/node.py#L328)）：

```python
if isinstance(message, dict):
    content = message.get("content", "")
    message_type = str(message.get("type", "ai")).lower()
else:
    content = getattr(message, "content", str(message))
    message_type = str(getattr(message, "type", "ai")).lower()
```

**作用**：`message` 有两种来源形态——

1. **dict**：刚从 JSON / 配置文件 / 反序列化 → 用 `.get()` 读字段
2. **LangChain 消息对象**：已经在内存里 → 用 `getattr` 读属性

`create_message` 把这两种**统一**为 LangChain 的 `BaseMessage`（HumanMessage / AIMessage），下游 `agent.invoke()` 就能只认一种类型。

类似的类型分流在 57、79、167、220、376、384、390 行反复出现，**统一模式**都是先 `isinstance` 分流再分别取值。

#### 为什么不直接 `type(x) == dict`

因为 `dict` 子类（`OrderedDict`、Pydantic 模型、自定义 dict 后代）过 `isinstance` 但不过 `type is` 检查——用前者**容错更宽**。

---

### 2.2 `getattr(obj, name, default)` — 读属性（第 332、386 等行）

`getattr` = **get attribute**（"拿属性"），不是缩写。

#### 语法

```python
getattr(object, name, default)
#          对象       属性名   可选默认值（缺则抛 AttributeError）
```

等价于 `object.name`，但**属性名字符串是运行时算出来的**——允许动态取值。

#### 和 `isinstance` 的区别

| 函数 | 问的问题 | 作用 |
|------|----------|------|
| `isinstance(obj, cls)` | "你是谁？"（类型） | 类型检查 |
| `getattr(obj, "x")` | "你有没有叫 x 的东西？"（属性） | 属性读取 |

#### 在 node.py 的用途

与 2.1 配对出现（[node.py:332](src/core/node.py#L332)）：

```python
content = getattr(message, "content", str(message))
#          有 content 属性？ 用它的值。 没有？ 把整个对象转字符串兜底

message_type = str(getattr(message, "type", "ai")).lower()
#                              默认 "ai"：没标类型的消息默认当 AI 消息
```

另一处（[node.py:386](src/core/node.py#L386)）是 `safe_get` 助手：

```python
def safe_get(obj, key, default=""):
    if isinstance(obj, dict):
        return obj.get(key, default)     # dict 用 .get
    return getattr(obj, key, default)    # 对象用 getattr
```

对 "可能是 dict 也可能是对象" 的东西统一取值，下游 `safe_get(output, "messages", [])` 就是这种场景。

#### 反射四件套

| 函数 | 作用 |
|------|------|
| `getattr(obj, name, default)` | 读属性，缺则返默认值 |
| `setattr(obj, name, value)` | 写属性 |
| `hasattr(obj, name)` | 布尔判断：有没有 |
| `delattr(obj, name)` | 删属性 |

这套反射机制让代码能在**运行时审视任意对象内部结构**——动态属性名、序列化/反序列化、插件体系都常用。

---

### 2.3 `hasattr(obj, name)` — 布尔探测（第 367 行）

`hasattr` 是 `getattr` 的布尔兄弟：底层其实就是 `try: getattr(obj, name); return True; except AttributeError: return False`。

#### 在 node.py 的核心用途（第 367、515 行）

```python
invoke_state = state.dict() if hasattr(state, "dict") else dict(state)
```

这不是"功能探测"，是**类型适配**。项目里 `State` 有两种可能的身份：

| 类型 | 例子 | 怎么转 dict |
|------|------|-------------|
| Pydantic 模型 | `class State(BaseModel)` | 自带 `.dict()` 序列化方法 |
| 普通 dict | `{"messages": [...]}` | 没有 `.dict()`，用 `dict(...)` 浅拷贝 |

`hasattr(state, "dict")` 探测"你自带序列化吗"——有就走 Pydantic 高保真路径（保留嵌套模型、字段校验），没有就走内置工厂。

同样的写法在 `refiner_node`（:515）又出现了一次——**同一模式复制粘贴，不是偶然**："构造传给 agent 的 dict 快照" 这件事实质相同，只是 `messages` 怎么改有差异。

**副产品**：先拷贝再改（`:368 invoke_state["messages"] = ...`），避免原地改 `state`——LangGraph 要求状态更新**必须产生新 dict，不能改旧对象**。

---

### 2.4 `import sys` + `sys.stdin.isatty()` — 交互探测（第 275、283、303 行）

#### `isatty()` 的含义

`sys.stdin.isatty()` 返回 `True` 当且仅当**标准输入连接的是真正终端（TTY）**。

| 场景 | 返回值 |
|------|--------|
| 终端 / PowerShell 直接运行 | `true` |
| 重定向 `< input.txt` | `false` |
| 管道 `echo "2" \| python` | `false` |
| 后台进程 / cron / VS Code 接管 | `false` |

#### 解决什么问题

`human_choice_node`（[node.py:264-316](src/core/node.py#L264-L316)）是流程中唯一**暂停等输入**的节点。如果跑在管道/后台/CI 里没人回答 `input()`，进程**永久挂起**。

`isatty()` 提供了干净的降级：

```python
choice = "2"
if sys.stdin.isatty():
    while True:
        try:
            choice = input("Please enter your choice (1 or 2): ")
        except (EOFError, KeyboardInterrupt):
            choice = "2"       # Ctrl+D / Ctrl+C 也兜底到 2
            break
        if choice in ["1", "2"]:
            break
        print("Invalid input, please try again.")
else:
    print("[auto] Non-interactive mode, defaulting to choice 2 (continue)")
```

- 交互 → 真正问用户，输入 1 重跑、2 继续，非法就重问
- 非交互 → 静默选 2，打印 `[auto]` 提示

**注意**：`import sys` 在**函数内部**（:275）——这是合理的，`sys` 只在 `human_choice_node` 才用到，延迟导入减小启动开销。

Windows 11 上同样有效——PowerShell 直接运行为 `true`，管道为 `false`，行为一致。

---

## 三、节点的数值型约定：三段切片（第 355-363 行）

`note_agent_node` 处理长消息**不是**全量压缩，而是**三段式切片**：

```python
if len(current_messages) > 6:
    head_messages   = list(current_messages[:2])   # 头 2 条
    tail_messages   = list(current_messages[-2:])   # 尾 2 条
    processing_messages = list(current_messages[2:-2])  # 中间段
```

假设 10 条输入：

```
[0] System "你是个科研助手"      \
[1] Human "起个假设"              /  head_messages（保：系统提示+首轮意图）
[2] AI    "假设A：温度↑→产量↑"   \
[3] Human "搜一下文献"             |
[4] AI    "找到3篇支持"            |  processing_messages（喂给 NoteAgent）
[5] Human "做个实验"              |
[6] AI    "实验数据…"             |
[7] Human "画个图"               /
[8] AI    "折线图<chart.png>"     \  tail_messages（保：最近上下文）
[9] Human "现在起新假设"          /
```

**Why head**：系统提示 + 首轮人类意图，源方向不能丢。
**Why tail**：最近几轮的关键信息，LLM 靠它接上下文。
**Why 牺牲中间**：最长、最可裁剪。

**硬编码提醒**：阈值 `6`、保留数 `2/2` 都是写死的整数，后续换 SummarizationMiddleware 或调参时记得联动。

---

## 四、为什么不用 LangChain SummarizationMiddleware

`note_agent_node` 是手工的"对话压缩"，而 LangChain 有官方的 `SummarizationMiddleware` 做近似的事。**项目为何不用？**

| 维度 | SummarizationMiddleware | note_agent_node |
|------|--------------------------|-----------------|
| 触发 | LLM 调用前自动检测 token 超限 | 工作流调度（router 决定）主动触发 |
| 能读产物文件 | ❌ 只看对话历史 | ✅ 读报告/图表/代码产出 |
| 摘要来源 | 纯对话再总结 | 对话 + 产物**双路融合** |
| 摘要位置 | 插入系统提示附近 | 精准替换"中间段"头尾原位保留 |
| 字段名 | `summary` 固定 | `output.messages` 自定义字段链可控 |
| 路由联动 | 完全解耦 | router 可直接决定触发时机 |
| 质量反馈 | ❌ | ✅ `quality_feedback`、`needs_revision` 联动 |
| 产物状态刷新 | ❌ | ✅ `search_artifacts` / `data_viz_artifacts` / `code_artifacts` / `report_artifacts` |
| 多模型 | ❌ 仅 `ChatAnthropic` 能用 | ✅ 兼容 ChatAnthropic/OpenAI/Azure/Google/Ollama/Groq/OpenRouter 全部 7 个适配器 |

**核心分歧**：`note_agent_node` 不只是"摘要"——它是**全状态重映射**。SummarizationMiddleware 做不到"重写 `hypothesis`、更新 `quality_feedback`、刷新 `*_artifacts`" 这一整套动作。

### 可以被替换的信号

以下任一成立时考虑切换：

1. 形态从"科研工作流"变"纯对话"（没有产物文件）。
2. LLM provider 切到纯 Anthropic 单 provider。
3. 希望压缩变成零开发的默认行为。

### 代码组织上的好迹象

`:355-363` 切片、`:367` 状态构造、`:388-412` 字段映射，**三者写在同一个函数里但内边界清晰**。替换切片段不会影响状态映射段——框架上**留了嫁接点**。

---

## 五、refiner_node 与 note_agent_node 为何不冲突

直觉上两个节点都在"改写 messages"，易被误认为抢地盘。事实上**完全互补**。

### 5.1 入口不同

| | note_agent_node | refiner_node |
|--|--|--|
| 读什么 | 内存里的 `state.messages` | 文件系统 `WORKING_DIRECTORY/*.md` |
| 怎么读 | 三段切片 | `*Section 4.2 below |
| 喂给 agent | 裁剪后的 `processing_messages` | 单条 `HumanMessage(报告)` |

### 5.2 出口不同

`note_agent_node`：**原地改写**整段历史 + 全状态重写（:394-412）。

`refiner_node`：在现有 messages **后追加 1 条** AIMessage，不改其他字段（:521-523）。

`refiner` 跑完后**不会抹掉** `note_agent_node` 刚拼好的压缩结果——只是**追加**精炼意见。两个节点对 `messages` 的写方式不同，本质是**串行叠加**不是**并发覆写**。

### 5.3 时序保证

LangGraph 路由器执行顺序：

```
hypothesis → search → code → visualization → note_agent → refiner → back_to_hypothesis （条件回炉）
```

先 note 记录 → 后 refiner 翻案。两者**不会并发**；且 `needs_revision`/:408 字段确保 refiner 触发时不会误串行化。

### 5.4 形态上的对称

两个节点结构几乎镜像：

```python
invoke_state = state.dict() if hasattr(state, "dict") else dict(state)
X["messages"] = ...
result = agent.invoke(X)
```

但**做的事方向相反**：

- `note_agent_node`：**缩短**（压缩对话）
- `refiner_node`：**扩写**（把多文件意见加进历史）

构成循环：
`[搜索+实验+画图] → 越来越长 → note 压缩 → 还太长？ → refiner 评估+决定回炉`

---

## 六、refiner_node 的具体实现

### 6.1 收集阶段（:506-512）

```python
materials = []
for fpath in storage_path.glob("*.md"):
    with open(fpath, "r", encoding="utf-8") as f:
        materials.append(f"MD file '{fpath.name}':\n{f.read()}")
combined_materials = "\n\n".join(materials)
report_content = f"Report materials:\n{combined_materials}"
```

- `Path.glob`：非递归——只顶层 `.md`，**排除** README/LICENSE 等子目录物料的干扰
- `encoding="utf-8"`：Windows 下不写容易 GBK 错乱
- `with open`：自动管理句柄，读炸也关
- `"MD file 'xxx.md':\n..."`：每段**带文件名前缀**；`\n.` 其实应为 `\n`

#### 为什么用双换行 `\n\n`

- 单换行 `\n` = 同一段内换行，文件分界靠前缀人肉识别
- 双换行 `\n\n` = 段落分隔，Refiner 能一目了然

```
Report materials:
MD file 'hypothesis.md':
初步假设…
                                                   ← 空行把文件分开
MD file 'search_report.md':
已搜3篇…

MD file 'code_review.md':
…
```

### 6.2 喂给 agent（:515-519）

```python
refiner_input = state.dict() if hasattr(state, "dict") else dict(state)
refiner_input["messages"] = [HumanMessage(content=report_content)]
result = agent.invoke(refiner_input)
output = result.get("messages")[-1].currentMessages 整体换成单条 HumanMessage——Refiner 的**输入**是所有 .md 文件的整合，**输出**是最末尾一条 AIMessage。

### 6.3 追加结果（:521-525）

```python
current_messages = list(get_state_attr(state, "messages", []))
return {
    "messages": current_messages + [AIMessage(content=output, name=name)],
    "last_active_agent": name,
}
```

只写 `messages`、不写 `hypothesis`/`*_artifacts`/`needs_revision`——`refiner` 是"提意见的"不是"改主意的"。

### 6.4 让 Refiner 能读多文档的三种范式（此处选用第一种）

| 范式 | 代表 | 优劣 |
|------|------|------|
| 单消息 + 分隔符 | refiner_node | 实现简单、长文档易爆上下文 |
| 多消息 + 文件名 | 每文件一条 HumanMessage | 注意力更聚焦、但丢失跨文件关系 |
| RAG 检索 | 向量数据库按需召回 | 量大了最合适、但引入额外基建 |

DatAGEN 当前规模下第一种**够用且省事**。当 `.md` 总和经常超 10k token 再考虑 RAG。

### 6.5 两处小瑕疵

1. **未递归**：`.glob("*.md")` 不扫子目录——这是刻意设计，换 `.rglob("*.md")` 才扫得到。

2. **未排序**：`glob()` 顺序依赖文件系统——同一次运行不保证一样。建议：

   ```python
   sorted(storage_path.glob("*.md"), key=lambda p: p.name.lower())
   ```

   跨平台顺序才稳定。

---

## 七、节点不只四个——完整节点清单

前面三节聚焦 `human_choice_node` / `create_message` / `note_agent_node` / `refiner_node`。但 grep 整个文件 `def xxx_node(` 会发现**实际有 5 个 `_node` 函数**：

| 函数 | 起点 | 职责 |
|------|------|------|
| `agent_node` | L191 | 通用 Agent 调用节点——调 `agent.invoke(state)`、抽 `get_structured_output`、把结果拼回 State。**所有"工作角色"共用** |
| `human_choice_node` | L264 | 工作流中唯一暂停等人工输入的节点（§2.4 详述） |
| `note_agent_node` | L338 | 读产物文件 → 三段式压缩中间 messages → 全状态重映射（§4 详述） |
| `human_review_node` | 437 | 与 `human_choice_node` 形态相似但用于 `quality_review` 后的**人工审评** |
| `refiner_node` | 491 | 读 `.md` → 拼条 → Refiner 精炼 → 追加 AI 消息（§5-§6 详述） |

此外还有 5 个文件内辅助函数（非 `_node`）支撑上层：

| 辅助函数 | 行号 | 作用 |
|----------|------|------|
| `get_state_attr` | 46 | 安全读 State 属性（兼容 dict / Pydantic） |
| `update_artifact_dict` | 62 | 更新 `search_artifacts` 等产物字段 |
| `safe_get_content` | 93 | 从任意对象里抠文本内容 |
| `extract_json_from_text` | 120 | 从 LLM 文本输出里抠 JSON（fallback 解析） |
| `get_structured_output` | 156 | 从 agent 返回里抽出结构化结果——**是判断输出到底走 Pydantic 还是 dict 路径的关键** |

项目 agents/ 下共 10 个具体 Agent 文件（除 `factory.py` 外全继承 `BaseAgent`）：`code_agent.py`、`hypothesis_agent.py`、`note_agent.py`、`process_agent.py`、`quality_review_agent.py`、`refiner_agent.py`、`report_agent.py`、`search_agent.py`、`visualization_agent.py`——**节点和 agent 并不是一一对应**：`agent_node` 是共享的，真正"专属节点"只有 `note_agent_node` / `refiner_node` / `human_choice_node` / `human_review_node` 这四个。

---

## 八、`refiner_node` / `note_agent_node` 不是动态调用——workflow 里是静态绑定

有人怀疑"两个同名节点是不是通过反射选出来的"。查 `src/core/workflow.py`:

```python
# workflow.py L25——静态 import
from .node import agent_node, human_choice_node, note_agent_node, human_review_node, refiner_node
# workflow.py L109——闭包内直接调用
return note_agent_node(cast(State, state), agent, name)
# workflow.py L113
return refiner_node(cast(State, state), agent, name)
```

——**没有任何 `globals()`/`getattr(`/字符串拼接式调用**。`workflow.py` 里有路由逻辑决定哪个闭包被跑，但函数体本身是"哪个实例调到来决定"。

---

## 九、代码坏味道（code smell）— `:399-400` 的"备选字段名链"是 dead code

### 9.1 代码长这样

```python
"current_instruction": str(safe_get(output, "current_instruction", safe_get(output, "process", ""))),
"next_workflow_step":  str(safe_get(output, "next_workflow_step", safe_get(output, "process_decision", ""))),
"search_artifacts":   str(safe_get(output, "search_artifacts",    safe_get(output, "searcher_state", ""))),
"data_viz_artifacts": str(safe_get(output, "data_viz_artifacts",  safe_get(output, "visualization_state", ""))),
"code_artifacts":     str(safe_get(output, "code_artifacts",      safe_get(output, "code_state", ""))),
"report_artifacts":   str(safe_get(output, "report_artifacts",    safe_get(output, "report_section", ""))),
"quality_feedback":   str(safe_get(output, "quality_feedback",    safe_get(output, "quality_review", ""))),
```

### 9.2 所有 NoteOutput 的字段名是**固定的 Pydantic**

打开 `src/agents/note_agent.py:28`，`NoteOutput` 的字段清单如下：

- `messages` / `hypothesis` / `current_instruction` / `next_workflow_step`
- `search_artifacts` / `data_viz_artifacts` / `code_artifacts` / `report_artifacts`
- `quality_feedback` / `needs_revision`

——每一个都**直接对应** State 字段名。上一栏的备选名：

> `"process"` / `"process_decision"` / `"searcher_state"` / `"visualization_state"` / `"code_state"` / `"report_section"` / `"quality_review"`

**在 NoteOutput 和其他任何 agent 输出 schema（`QualityOutput` / `ProcessRouteSchema` / `ArtifactSchema`）中都不存在**。

### 9.3 `safe_get` 本身合理，但备选链是历史遗留

`safe_get` 兼容 dict / Pydantic 两种访问方式，是不错的防御写法。但 `safe_get(x, "主名字", safe_get(x, "备选名字", ""))` 的**备选名字永远不会命中**——没有任何代码 path 会产生叫 `"searcher_state"` 的字段。

### 9.4 影响

- **阅读障碍**：读代码时要去追"备选名从哪来"，发现找不到，造成认知浪费。
- **暗示性污染**：后续维护者可能误以为真的有字段漂移场景，从而仿照这个模式写更多的备选链——**冗余代码扩散**。
- **底线**：功能上无害（永远不会出错），但 **dead code 没有任何收益却持续产生阅读成本**。

### 9.5 建议的正确写法

**简化方案**（主字段直取，Pydantic 字段必存在）：

```python
"current_instruction": str(getattr(output, "current_instruction", "")),
"next_workflow_step":  str(getattr(output, "next_workflow_step",  "")),
```

或者更激进——直接用 `output.current_instruction`（Pydantic 保证字段存在，不存在就是Class定义错，这时候让它 raise 反而**对**）。

如果要保留防御性（预防 LLM 偶尔输出 dict 而非 Pydantic），可以**只保留一层**：

```python
"current_instruction": str(safe_get(output, "current_instruction", "")),
```

——不再嵌套备选链。

### 9.6 对"设计模式复盘"项的联动修正

`§六 设计模式复盘` 第 4 项写着 `字段名备选链（:399-400）：agent 输出字段漂移也不 crash`——**这是一个错误叙述，不应被后人视作"推荐模式"**。我已把那一条标记为删除线并指向本节。

`safe_get` 双通道（dict 或 Pydantic）本身仍是合理模式，只是**应当只保留一层主字段名，不再嵌套备选字段名链**。

---

## 十、`human_choice_node` 的可测性为零

`human_choice_node`（`isatty` 分支 + 重试循环 + EOFError / KeyboardInterrupt + 选 1 的 "specify areas" 分支）**一行测试都还没写**。这并非夸大——查：

- `tests/` 下只有 `test_agent_node.py` / `test_debug_hypothesis_node.py` / `学习/test_asyncio_order.py`，**零个**测试调用 `human_choice_node` 或直接 mock `sys.stdin.isatty`。
- grep 整个 `tests/`：**`MagicMock` / `patch` / `isatty` 任一都没出现**（`MagicMock`/`patch` 仅在 `.claude/settings.json` 历史命令和 `学习/pytest断点调试配置.md`）。
- grep **`sys.stdin.isatty`**：**仅 `node.py` 一处** 定义。

### 跳过机制也不存在

`main.py` 仅 `sys.stderr` 被 `OutputFilter` 替换过，**`sys.stdin` 从未被替换 / 重定向**，工程里没有 `headless` / `non_interactive` 标志位。`workflow.py` 里 `add_edge("Hypothesis", "HumanChoice")` 是**无条件硬边**——没有任何环境变量 / 状态位能跳过人工选择。`human_review_node`（node.py:456，也用一次 `isatty`）同样没有跳过机制。

### Windows 11 下 `isatty()` 的实际行为

……**跟 PowerShell / Windows Terminal / Git Bash / VS Code Integrated Terminal 的官方文档保证其实很弱**。

CPython `isatty()` 底层是 `GetFileType(STD_INPUT_HANDLE) + _isatty()`：

| 来源 | `isatty()` |
|------|------------|
| conhost / Windows Terminal / PowerShell 直接跑 | `true` |
| MSYS2 / Git Bash | 通常 `true`（POSIX 伪终端） |
| **VS Code Integrated Terminal** | **跨版本不一致**——旧版 conpty 下伪终端让 `isatty()` 返回 **`false`**，新版才改 `true`。**在旧版 VS Code 里跑 DatAGEN 会被"自动选 2"而无法人工选择**。 |
| 管道 `< file.txt` / `cmd1 \| cmd2` | `false` |
| 后台 / cron | `false` |

Python 官方文档**只保证"重定向返回 False"**，对具体终端模拟器**没有官方文档保证**返回值。所以'学习/node.md:188' 讲的"Windows 11 同样有效"是经验结论**没文档背书**——在 VS Code 老版本下**早期确实踩过坑**。

### 把交互探测抽象成可注入的依赖

`sys.stdin` 在函数内部 `import sys` 后直接访问，想 mock 只能 `patch('sys.stdin')` 全局替换——**影响面过大**。更好的做法往往是在函数签名里注入一个 `_is_interactive` callable：

```python
def human_choice_node(state, agent, name, *, _is_interactive=sys.stdin.isatty):
    if _is_interactive():
        ...
```

- 默认行为不变（外部调用不用改）
- 测试可以传 `_is_interactive=lambda: True` 或 `lambda: False` 覆盖两条分支
- workflow.py 高层可以按配置跳过：

  ```python
  if os.getenv("DATAGEN_HEADLESS"):  # 不在函数内探测
      skip_to_next_node()
  else:
      human_choice_node(state, agent, name)
  ```

**——跳过人工选择应该是节点外的路由决定，不是节点内 `import sys` + `isatty()`**。后续若把 DatAGEN 跑回 CI / Docker（例如想自动回整轮测试），这条重构**是必要**的。

---

## 十一、折叠版 · 参考卡

### 节点全貌

| 节点 | 行号 | 必答 |
|------|------|------|
| `agent_node` | 191 | 调 `agent.invoke(state)` → 通用 Agent 调用节点（所有工作角色共用） |
| `human_choice_node` | 264 | 暂停问用户：交互 / 非交互二分支 + 重试循环 |
| `note_agent_node` | 338 | 读产物文件 → 三段切片压缩 → 全状态重映射 |
| `human_review_node` | 437 | quality_review 后的人工审评（与 `human_choice_node` 同族） |
| `refiner_node` | 491 | 工作目录 `.md` 全量 glob → 双换行拼接 → 追加 AI 精炼意见 |

辅助函数簇：`get_state_attr`(46) / `update_artifact_dict`(62) / `safe_get_content`(93) / `extract_json_from_text`(120) / `get_structured_output`(156)。

### 行号速查

| 行号 | 语法 / 惯用 | 作用 |
|------|---------|------|
| 46-155 | 辅助函数簇 | `get_state_attr` / `update_artifact_dict` / `safe_get_content` / `extract_json_from_text` / `get_structured_output` |
| 156 | `get_structured_output` | 抽出 agent 的结构化结果（判断 Pydantic / dict / JSON fallback） |
| 191-260 | `agent_node` | **通用** Agent 调用节点  |
| 264-316 | `human_choice_node` | 工作流中唯一暂停等用户输入的节点 |
| 275 | `import sys`（函数内） | 延迟导入 |
| 283、303 | `sys.stdin.isatty()` | 交互 vs 非交互探测 |
| 284-292 | `while True` + `try/except` | 问到达法输入或 Ctrl+C/D 才推 |
| 319-335 | `create_message` | dict / 对象 → `BaseMessage` 统一 |
| 328、332、333 | `isinstance` + `getattr` | 双形态分流取值 |
| 338-414 | `note_agent_node` | 产物压缩 + 全状态重映射 |
| 356-363 | 三段切片 | 上下文窗口管理 |
| 367、515 | `hasattr(state, "dict")` | Pydantic / dict 双兼容，写前拷贝 |
| 382-386 | `safe_get` 反射双通道 | `obj[key]` 或 `obj.key` 统一 |
| 388-412 | 语义 / 产物 / 质量映射 | agent 输出 → State 各字段 |
| 437-485 | `human_review_node` | quality_review 后的人工审评节点（与 human_choice 同族） |
| 491-531 | `refiner_node` | 读 .md → 拼装 → 追加 AI 意见 |
| 506-512 | `glob("*.md")` + `\n\n` 拼接 | 批量拾取 + 双换行分段 |
| 516、519 | `input["messages"] = [单条]` | 多文档塞进一条 HumanMessage |

### 三对黄金搭档

| 搭档 | 一起出现的位置 | 分工 |
|------|----------------|------|
| `isinstance` + `getattr` | 328-333，全文 | 先分流（类型），后取值（属性） |
| `hasattr` + `getattr` | 367，386，515 | 先探测（有吗），后读（取值） |
| `isinstance` + `dict()` | 367，515 | Pydantic 走 `.dict()`，dict 走 `dict()` |

### 设计模式复盘（修订后）

1. **非交互优雅降级**（`isatty`）：管道中不挂起。
2. **三段式中段裁剪**（head/tail + processing）：省 token 同时保系统提示和最近上下文。
3. **写前拷贝 + 新 state 返回**（`:367-368`）：遵守 LangGraph 状态不可变约定。
4. ~~**字段名备选链**~~ → **§九** 揭露为 dead code，**不应效仿**。
5. **产物文件 → 单 HumanMessage**（refiner）：最轻量的 RAG-less 多文档喂法。
6. **异常兜底**（`:416-418`、`:527-530`）：不让工作流中途断掉。
7. **跳过人工选择应在节点外决策**——`§十` 详述。

### 「假设数据流转」小抄

以 §三 的 10 条 messages 作输入，`note_agent_node` 内部依次生成：

- `head = [0,1]`，`processing = [2,3,4,5,6,7]`，`tail = [8,9]`
- `invoke_state.messages = [2,3,4,5,6,7]`
- `agent.invoke` 返回 `output.messages = [AIMessage("摘要：…")]`
- `messages = [AIMessage]`（新 messages 非空，用新）
- `combined_messages = [0, 1] + [摘要] + [8, 9]` → 从 10 条压到 5 条
- 写回 `updated_state.messages` 并**全字段写回**

`refiner_node` 跑在后面时：

- `glob` 到 3 个 `.md` → `materials = ["MD file 'hypothesis':…", "MD file 'search':…", "MD file 'code':…"]`
- `\n\n`.join → `report_content`
- `refiner_input = state.dict(); refiner_input["messages"] = [HumanMessage(report_content)]`
- `result.get("messages")[-1].content` → Refiner 意见字符串
- `current_messages + [AIMessage(意见)]` → 原 messages 不动，后附 1 条

### code smell 清单

| 位置 | 问题 | 见 |
|------|------|----|
| 399-400 | "字段名备选链" 是 dead code——所有 NoteOutput / QualityOutput / ArtifactSchema / ProcessRouteSchema 的字段名都**固定**，`"process"` / `"searcher_state"` 等备选名永远不会命中 | §九 |
| 283, 303, 456 | `isatty` 交互分支**零测试**，workflow 无跳过机制，Windows VS Code Integrated Terminal 下**返回值跨版本不一致** | §十 |
| 505 | `storage_path.glob("*.md")` 不递归，可能漏子目录物料；未排序，跨平台顺序不稳定 | §6.5 |
| 356-363 | 阈值 6 / 保留数 2/2 硬编码，换框架或调参时需联动 | §3 |
| 367-368 / 515 | `hasattr(state, "dict")` 写前拷贝模式在 `node.py` 内重复，可抽 helper | §2.3 |

### 改造方向速查

| 现状 | 改造后 |
|------|--------|
| `safe_get(x, "主名", safe_get(x, "备选", ""))` 双层嵌套 | `safe_get(x, "主名", "")` 或 `getattr(x, "主名", "")`（§九） |
| `human_choice_node` 内 `import sys` + `sys.stdin.isatty()` | 注入 `_is_interactive=sys.stdin.isatty` 关键字参数（§十） |
| workflow 里 `add_edge("Hypothesis", "HumanChoice")` 无条件 | 按 `os.getenv("DATAGEN_HEADLESS")` 跳过，或注入条件边（§十） |
| `glob("*.md")` 不递归不排序 | `sorted(storage_path.rglob("*.md"), key=lambda p: p.name.lower())`（§6.5） |
| 阈值 `6` / 保留 `2/2` 硬编码 | 抽成 `NOTE_AGENT_MAX_MESSAGES=6`、`NOTE_AGENT_HEAD_TAIL=2` 常量 |
