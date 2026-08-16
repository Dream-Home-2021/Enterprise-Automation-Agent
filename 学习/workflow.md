# workflow.py 节点注册机制详解

## 目录
- [核心问题](#核心问题)
- [LangGraph 的调用约定](#langgraph-的调用约定)
- [两种注册方式对比](#两种注册方式对比)
- [闭包（Closure）](#闭包closure)
- [cast 类型断言](#cast-类型断言)
- [完整流程走读](#完整流程走读)
- [类比代码](#类比代码)

---

## 核心问题

```python
self.workflow.add_node("HumanChoice", human_choice_node)       # 方式 A：直接传
self.workflow.add_node("Hypothesis", _wrap_agent_node(...))    # 方式 B：包装后传
```

**为什么有的节点能直接传函数，有的必须绕一层？**

答案在于**函数签名是否匹配 LangGraph 的调用约定**。

---

## LangGraph 的调用约定

LangGraph 注册节点后，运行时**只传一个参数 `state`**：

```python
# LangGraph 内部大致这样调用你注册的函数：
result = your_node_function(state)
```

所以注册的函数必须是**一元函数**（只接收 `state`）。

---

## 两种注册方式对比

### 方式 A：函数签名天然匹配 → 直接传

```python
# node.py 第 264 行
def human_choice_node(state: State) -> dict[str, Any]:
    ...

# node.py 第 436 行
def human_review_node(state: State) -> dict[str, Any]:
    ...
```

签名**恰好**是一元函数，LangGraph 传 `state`，函数能用。

```python
# workflow.py
self.workflow.add_node("HumanChoice", human_choice_node)    # ✅ 直接传
self.workflow.add_node("HumanReview", human_review_node)     # ✅ 直接传
```

### 方式 B：函数签名不匹配 → 闭包适配

```python
# node.py 第 191 行
def agent_node(state: State, agent: BaseAgent, name: str) -> dict[str, Any]:
    ...
```

这是**三元函数**——除了 `state`，还需要 `agent`（用哪个 agent）和 `name`（叫什么名字）。

如果直接注册：

```python
self.workflow.add_node("Hypothesis", agent_node)  # ❌
```

LangGraph 调用时只传 `state`：

```python
agent_node(state)   # TypeError: missing required argument 'agent' and 'name'
```

所以必须用**闭包**把额外参数"绑死"：

```python
# workflow.py 第 103-106 行
def _wrap_agent_node(agent, name):
    def action(state, config=None, store=None):
        return agent_node(cast(State, state), agent, name)
    return action
```

然后注册这个包装后的函数：

```python
                          参数1             参数2
self.workflow.add_node("Hypothesis", _wrap_agent_node(self.agents["hypothesis_agent"], "hypothesis_agent"))
```

---

## 闭包（Closure）

### 定义

一个**内部函数**"记住"了它被创建时外部函数的局部变量，即使外部函数已经执行完毕。

### 工作原理

```python
def _wrap_agent_node(agent, name):   # 外部函数：agent 和 name 是局部变量
    def action(state):                # 内部函数：引用了外层的 agent 和 name
        return agent_node(state, agent, name)
    return action                     # 返回内部函数对象（不是调用结果）
```

调用过程：

```python
# 步骤 1：调用外部函数，传入参数，返回内部函数
wrapped = _wrap_agent_node(self.agents["hypothesis_agent"], "hypothesis_agent")
# 此时 _wrap_agent_node 已执行完毕，但 wrapped（即 action）仍持有 agent 和 name

# 步骤 2：LangGraph 只传 state
result = wrapped(state)
# 等价于：agent_node(state, <hypothesis_agent 实例>, "hypothesis_agent")
```

### 类比代码

```python
def make_adder(x):
    def adder(y):
        return x + y    # adder 引用了外层的 x
    return adder

add5 = make_adder(5)    # x=5 被"关"在闭包里
print(add5(3))           # → 8  （5 + 3）
print(add5(10))          # → 15 （5 + 10）
```

| 类比 | workflow.py 对应 |
|------|-----------------|
| `make_adder(x)` | `_wrap_agent_node(agent, name)` |
| `adder(y)` | `action(state, ...)` |
| `x` 被关在闭包里 | `agent` 和 `name` 被关在闭包里 |
| `add5 = make_adder(5)` | `wrapped = _wrap_agent_node(self.agents["hypothesis_agent"], "hypothesis_agent")` |
| `add5(3)` → 8 | `wrapped(state)` → `agent_node(state, agent, name)` |

---

## cast 类型断言

### 源码

```python
# typing 模块里
def cast(typ, val):
    return val   # 什么都不做，原样返回
```

### 为什么用它

LangGraph 的节点函数签名里，`state` 的类型标注比较宽松（`Any` 或基类）。但 `agent_node` 需要把它当 `State` 用：

```python
# node.py 里 agent_node 内部会调用
state.dict()          # State 特有的方法
state.messages        # State 特有的属性
```

如果不用 `cast`，IDE 会报警告：`Any` 类型没有 `dict` 属性。

`cast(State, state)` 就是告诉类型检查器：

> "我知道类型标注不够精确，但我保证这个 `state` 实际上是 `State` 实例，别报警告。"

### 去掉会怎样

```python
def action(state, config=None, store=None):
    return agent_node(state, agent, name)   # 不用 cast
```

**运行时完全一样**，只是 IDE 可能会在 `state.dict()` 那行画黄色波浪线。

### 一句话总结

`cast` 是**给 IDE 和类型检查器看的提示**，对程序执行零影响。

---

## 完整流程走读

以 Hypothesis 节点为例：

```python
# 1. 创建 Agent 实例
self.agents["hypothesis_agent"] = agent_factory.create_agent("hypothesis_agent")

# 2. 包装函数（闭包）
#    外部函数 _wrap_agent_node 接收 agent 和 name，返回内部函数 action
#    action 捕获了 agent 和 name
wrapped = _wrap_agent_node(self.agents["hypothesis_agent"], "hypothesis_agent")

# 3. 注册节点
self.workflow.add_node("Hypothesis", wrapped)

# 4. LangGraph 运行时调用（只传 state）
result = wrapped(state)
#   内部：action(state)
#   内部：return agent_node(cast(State, state), agent, name)
#   等价于：agent_node(state, self.agents["hypothesis_agent"], "hypothesis_agent")

# 5. agent_node 执行逻辑
#    - 调用 agent.invoke(state)
#    - 提取结构化输出
#    - 构造 updates dict
#    - 返回 updates（LangGraph 用它更新全局状态）
```

---

## 总结表

| 节点 | node 函数 | 签名 | 注册方式 | 原因 |
|------|----------|------|----------|------|
| HumanChoice | `human_choice_node` | `(state)` | 直接传 | 一元函数，天然匹配 |
| HumanReview | `human_review_node` | `(state)` | 直接传 | 一元函数，天然匹配 |
| Hypothesis | `agent_node` | `(state, agent, name)` | 闭包包装 | 三元函数，需要绑定额外参数 |
| Process | `agent_node` | `(state, agent, name)` | 闭包包装 | 同上 |
| ... 等 | `agent_node` | `(state, agent, name)` | 闭包包装 | 同上 |
| NoteTaker | `note_agent_node` | `(state, agent, name)` | 闭包包装 | 同上 |
| Refiner | `refiner_node` | `(state, agent, name)` | 闭包包装 | 同上 |

**核心原则**：签名匹配 → 直接传；签名不匹配 → 闭包适配。