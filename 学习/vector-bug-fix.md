# 向量存储 Bug 修复总结

**日期**: 2026-06-24  
**文件**: `agent/db/postgres.py`, `agent/memory/profile.py`, `test/test_long_term_memory.py`

---

## Bug 1: embedding 向量维度不匹配

**现象**: 调用 `_save_vectors_async` 后，`agent_memory_vectors` 表无数据写入，且无任何错误日志（被 `try/except` 吞掉）。

**根因**: 
- 数据库 DDL 定义 `embedding vector(1536)`
- DashScope `text-embedding-v3` 实际返回 **1024 维**向量
- `INSERT` 时维度不匹配报错，被 `except Exception` 静默捕获

**修复**:
```sql
-- 已执行 ALTER TABLE 修改已有表
ALTER TABLE agent_memory_vectors ALTER COLUMN embedding TYPE vector(1024);
```
```python
# postgres.py DDL 定义改为 vector(1024)
embedding   vector(1024) NOT NULL,
```

---

## Bug 2: asyncpg 参数类型不匹配 — embedding

**现象**: `save_memory_vector` 报错 `invalid input for query argument $4: ... (expected str, got list)`

**根因**: 
- `save_memory_vector` 接收 `embedding: list[float]`
- SQL 中 `$4::vector` 要求字符串格式 `"[1.0,2.0,...]"`
- asyncpg 无法自动将 Python list 转为 pgvector 类型

**修复** (`postgres.py`):
```python
# 将 list[float] 转为 pgvector 字符串格式
emb_str = "[" + ",".join(str(v) for v in embedding) + "]"
await conn.execute(
    "... VALUES ($1, $2, $3, $4::vector, $5::jsonb)",
    user_id, session_id, content, emb_str, meta_str,
)
```

---

## Bug 3: asyncpg 参数类型不匹配 — metadata

**现象**: `save_memory_vector` 报错 `invalid input for query argument $5: {'source': ...} (expected str, got dict)`

**根因**: `metadata` 参数传入 Python dict，但 `$5::jsonb` 需要 JSON 字符串。

**修复** (`postgres.py`):
```python
meta_str = json.dumps(metadata or {})
await conn.execute(
    "... VALUES ($1, $2, $3, $4::vector, $5::jsonb)",
    user_id, session_id, content, emb_str, meta_str,
)
```

---

## Bug 4: 消息长度过滤阈值过高

**现象**: 中文消息被全部过滤，`texts` 为空列表，函数在第 219 行提前 return。

**根因**: 
- 过滤条件 `len(content) > 10` 
- 中文一个字符长度为 1，短消息如"我喜欢打篮球"(6)、"每周打三次"(5) 全部 < 10

**修复** (`profile.py`):
```python
# 阈值从 >10 改为 >= 5，兼容中文短消息
if len(content) >= 5:
    texts.append(content[:500])
```

---

## Bug 5: 批量 embedding 超过 API 限制

**现象**: 当用户消息 > 10 条时，报错 `batch size is invalid, it should not be larger than 10`

**根因**: DashScope `text-embedding-v3` 单次批量上限 **10 条**，代码未分批。

**修复** (`profile.py`):
```python
BATCH_SIZE = 10
all_embeddings: list[list[float]] = []
for batch_start in range(0, len(texts), BATCH_SIZE):
    batch = texts[batch_start : batch_start + BATCH_SIZE]
    response = client.embeddings.create(
        model="text-embedding-v3",
        input=batch,
    )
    all_embeddings.extend(item.embedding for item in response.data)
```

---

## Bug 6: 外键约束导致测试/写入失败

**现象**: 报错 `violates foreign key constraint "agent_memory_vectors_session_id_fkey"` — session_id 在 agent_sessions 中不存在。

**根因**: `agent_memory_vectors.session_id` 有外键约束 `REFERENCES agent_sessions(id)`，但测试和某些场景下 session_id 对应的行未创建。

**修复** (`test_long_term_memory.py`): 测试中先 `create_session` 再调 `_save_vectors_async`，满足外键约束。

**保留外键约束的原因**: 便于级联删除（会话删除时自动清理向量数据）。

---

## 修复文件清单

| 文件 | 修复内容 |
|------|---------|
| `agent/db/postgres.py` | DDL `vector(1536)` → `vector(1024)`；`save_memory_vector` 参数类型转换；`search_memory_vectors` 参数类型转换 |
| `agent/memory/profile.py` | 消息长度阈值 `>10` → `>=5`；embedding 分批处理（每批 ≤10 条） |
| `test/test_long_term_memory.py` | 向量测试先创建 session；断言验证向量数据写入 |
| 数据库 | `ALTER TABLE agent_memory_vectors ALTER COLUMN embedding TYPE vector(1024)` |
