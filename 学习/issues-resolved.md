# 问题排查与解决记录

> 时间：2026/06/21  
> 项目：My Agent — HTML UI 替换 Gradio，Redis + PostgreSQL 持久化

---

## 1. `ImportError: cannot import name 'ToolNode' from 'langgraph.prebuilt'`

**现象**：启动 `main/app_html.py` 时报 `ImportError: cannot import name 'ToolNode'`。

**原因**：`langgraph>=1.2.0` 移除了 `langgraph.prebuilt` 子模块，`ToolNode` 不再存在。

**解决**：降级到 `langgraph==1.1.10`（该版本仍有 `ToolNode`）。

**代码位置**：
- `requirements.txt` — `langgraph>=1.1.10`
- `agent/supervisor/graph.py:17` — `from langgraph.prebuilt import ToolNode`
- `agent/agents/chat_agent.py:13` — 同上

---

## 2. `NotImplementedError` — `RedisSaver.aget_tuple()`

**现象**：发送消息时 `AsyncPregelLoop.__aenter__` 调用 `checkpointer.aget_tuple()` 抛出 `NotImplementedError`。

**原因**：`agent/memory/short_term.py` 用的是同步 `RedisSaver`，它只实现了 `get_tuple()`（同步），没有 `aget_tuple()`（异步）。LangGraph 1.x 的 `astream()` 走的是 `AsyncPregelLoop`，必须用异步检查点。

**流程**：
```
agent/service.py:60  supervisor.astream()
  → langgraph/pregel/_loop.py:1450  AsyncPregelLoop.__aenter__()
    → checkpointer.aget_tuple()  ← NotImplementedError
```

**解决**：改用 `AsyncRedisSaver` 并调用 `await setup()`。

**代码位置**：
- `agent/memory/short_term.py` — `make_checkpointer()` 改为 async，使用 `AsyncRedisSaver`
- `agent/service.py:33` — `await make_checkpointer()`
- `main/app_html.py:40` — `await make_generate_response()`

---

## 3. `RedisSearchError: Cannot create index on db != 0`

**现象**：`AsyncRedisSaver.setup()` 创建 RediSearch 索引时报错。

**原因**：RediSearch 索引只能在 Redis DB 0 上创建。`.env` 里配置的是 `redis://localhost:6380/1`（DB 1）。

**解决**：`.env` 改为 `redis://localhost:6380/0`，`agent/db/redis.py` 默认值也改为 DB 0。

**代码位置**：
- `.env:23` — `AGENT_REDIS_URL=redis://localhost:6380/0`
- `agent/db/redis.py:16` — 默认值 `redis://localhost:6380/0`

---

## 4. 会话切换后历史消息丢失

**现象**：切换左侧会话列表项，右侧聊天区没有加载历史消息。

**原因**：`agent/memory/history.py` 用的是同步 `RedisSaver`，它没有 `alist()` 方法（只有 `AsyncRedisSaver` 有），导致 `load_conversation_history()` 永远返回空列表。

**流程**：
```
前端 switchSession()
  → GET /api/sessions/{id}/history
    → agent/memory/history.py:load_conversation_history()
      → checkpointer.alist()  ← 同步 RedisSaver 无此方法，返回 []
```

**解决**：`history.py` 改用 `AsyncRedisSaver` + `await setup()`。

**代码位置**：
- `agent/memory/history.py` — `_get_checkpointer()` 改为 async，使用 `AsyncRedisSaver`

---

## 5. 流式输出文字丢失

**现象**：SSE 流式回复时，前端显示的文字不完整，部分段落缺失。

**原因**：`service.py` 里 `content += chunk.content` 是累加操作，但 `astream(stream_mode="messages")` 返回的 `chunk.content` 本身就是**累积完整内容**，不是增量 delta。累加导致内容重复拼接，router 计算 delta 时出错。

**流程**：
```
LangGraph astream(messages) 返回：
  chunk #1: content='你好'
  chunk #2: content='！有什么'
  chunk #3: content='我可以帮您的'

service.py:75  content += chunk.content  →  '你好！有什么我可以帮您的' (正确)
但 router 那边用 len 算 delta，如果 content 已经累加过，delta 就会算错
```

**解决**：`service.py` 里改为 `content = chunk.content`（直接赋值，不累加）。router 那边已经用 `new_content[len(full_content):]` 算 delta，配合正确。

**代码位置**：
- `agent/service.py:75` — `content = chunk.content`（原来是 `content += chunk.content`）

---

## 6. 流式输出"一大段直接出来"（非逐 token）

**现象**：回复文字一次性全部显示，没有逐字打字机效果。

**原因**：`supervisor` 节点里用的是 `model.invoke()`（同步非流式），LLM 一次性返回完整响应，LangGraph 的 `astream` 只能拿到一个完整 chunk。

**流程**：
```
agent/supervisor/graph.py:75  model.invoke(messages)  →  一次性返回完整响应
  → LangGraph astream 只拿到 1-2 个 chunk
    → 前端收到一大段文字，无逐字效果
```

**状态**：**未修复**。要实现逐字流式需要把 `model.invoke()` 改成 `model.astream()`，但改动涉及节点函数从同步改为 async generator，影响较大，暂缓。

**代码位置**：
- `agent/supervisor/graph.py:75` — `model.invoke(messages)`

---

## 7. `upsert_profile` / `save_preference` 接口设计 bug

**现象**：测试用例调用 `upsert_profile(user_id, dict_value)` 时报 `TypeError: expected str, got dict`。

**原因**：函数签名声明 `profile_data: dict`，但 SQL 里用 `$2::jsonb`，asyncpg 要求传给 jsonb 列的是 JSON 字符串。调用方需要自己 `json.dumps()`，接口不透明。

**流程**：
```
upsert_profile(user_id, {"name": "Test"})
  → SQL: INSERT ... VALUES ($1, $2::jsonb, ...)
    → asyncpg 期望 $2 是 str，收到 dict → TypeError
```

**状态**：**未修复**（测试代码做了适配：传 `json.dumps(value)`）。

**修复建议**：在函数内部做序列化：
```python
profile_data = json.dumps(profile_data) if isinstance(profile_data, dict) else profile_data
```

**代码位置**：
- `agent/db/postgres.py:308` — `upsert_profile()`
- `agent/db/postgres.py:227` — `save_preference()`

---

## 依赖版本锁定

| 包 | 版本 | 原因 |
|----|------|------|
| `langgraph` | `==1.1.10` | 1.2.0+ 移除了 `ToolNode` |
| `langgraph-checkpoint-redis` | `0.4.1` | 配合 langgraph 1.1.10 |
| `redis` | `>=5.0` | async 支持 |
| `gradio` | 移除 | 替换为 HTML UI |
