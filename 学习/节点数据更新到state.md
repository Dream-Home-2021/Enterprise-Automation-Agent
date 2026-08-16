# 节点如何更新 State：Reducer 机制

## 一句话总结

节点不直接改 State，而是 **return 一个 update dict**，由 LangGraph 引擎用 **reducer** 把 update dict 合并进全局 State，再传给下一个节点。

## 调用链

```
节点函数 return {"messages": [...], "hypothesis": "xxx", ...}
        ↓
LangGraph StateGraph 接收这个 dict
        ↓
用 State 字段定义的 reducer 合并进全局 State
        ↓
合并后的新 State 传给下一个节点
```

## Reducer 合并规则

| 字段定义方式 | reducer 行为 |
|---|---|
| `messages` 带 `Annotated[..., add_messages]` | **追加**（新消息贴到末尾，len 只增不减） |
| `hypothesis: str` 等普通字段 | **覆盖**（新值替换旧值） |

**注意**：节点只需 return 它要更新的字段，没写的字段 LangGraph 保持原值——这是"部分更新"，不用把整个 State 包一遍。

## 本项目的节点 return 一览

所有节点函数在 [src/core/node.py](src/core/node.py) 里，它们的返回形态如下：

### `agent_node(state, agent, name)` — 通用节点（Hypothesis/Process/Coder/Search/Viz/Report/QualityReview）

```python
return {
    "messages": current_messages + [ai_message],   # 新 AIMessage 追加
    "last_active_agent": name,
    "step_count": current_step + 1,                # 每走一步 +1，防无限循环
    **agent.get_state_updates(state, output),      # 各 Agent 声明的产物更新（见各 Agent 的 get_state_updates）
    "completed_tasks": completed,                  # 如有 current_instruction 就记入已完成
}
```

### `human_choice_node(state)` — 用户选择"重新生成假设"还是"继续"

```python
# 选 1（重新生成）：
return {
    "messages": current_messages + [HumanMessage("Regenerate hypothesis...")],
    "hypothesis": None,                            # 清空假设
    "last_active_agent": "human"
}
# 选 2（继续）：
return {
    "messages": current_messages + [HumanMessage("Continue the research process")],
    "current_instruction": "Continue the research process",
    "last_active_agent": "human"
}
```

### `note_agent_node(state, agent, name)` — NoteAgent 专用（上下文窗口管理）

当消息 > 6 条时裁剪中间，只留首尾各 2 条；然后把 NoteAgent 的结构化输出语义映射回各字段：

```python
return {
    "messages":                              # 裁剪后拼接（覆盖，非追加！）
        head_messages + new_messages + tail_messages,
    "hypothesis": str(output.get("hypothesis", "")),
    "current_instruction":                   # 兼容老字段名
        str(safe_get(output, "current_instruction", safe_get(output, "process", ""))),
    "next_workflow_step":                    # 兼容老字段名
        str(safe_get(output, "next_workflow_step", safe_get(output, "process_decision", ""))),
    "search_artifacts":  update_artifact_dict({}, ...),
    "data_viz_artifacts": update_artifact_dict({}, ...),
    "code_artifacts":    update_artifact_dict({}, ...),
    "report_artifacts":  update_artifact_dict({}, ...),
    "quality_feedback":  str(...),
    "needs_revision":    bool(...),
    "last_active_agent": "note_agent",
}
```

### `refiner_node(state, agent, name)` — Refiner 汇总 .md 文件精炼

```python
return {
    "messages": current_messages + [AIMessage(content=output, name=name)],
    "last_active_agent": name,
}
```

### `human_review_node(state)` — 用户审核（是否修订）

```python
# 用户输入 yes（需要修订）：
return {
    "messages": [HumanMessage(req)],   # 覆盖为新请求
    "needs_revision": True,
    "last_active_agent": "human"
}
# 用户输入 no（结束）：
return {
    "needs_revision": False,
    "revision_count": 0,               # 重置计数器
    "last_active_agent": "human"
}
```

### 错误兜底 `_create_error_state`

```python
return {
    **state.dict(),                                      # 带上当前所有字段
    "messages": list(state.messages) + [error_message],  # 追加错误消息
    "last_active_agent": name,
}
```

## 关键点

- **State 不是直接赋值的**——节点拿不到 State 对象的引用，只能 return update dict
- **reducer 决定合并方式**——`add_messages` 追加 vs 普通字段覆盖
- **未声明的字段保留原值**——节点只需 declare"我要改什么"，不用包出完整 State
- **可回溯**——MemorySaver checkpointer 把每个节点的输入 State + return update 都记录下来（[workflow.py:196-197](src/core/workflow.py#L196-L197)）
