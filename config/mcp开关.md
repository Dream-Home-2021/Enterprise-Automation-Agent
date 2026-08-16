# MCP 全局开关

通过 Python 侧一个常量关闭/开启整个项目的 MCP 服务。
改动位于 `src/core/agent_config_loader.py`。

## 开关位置

```python
# 全局 MCP 总开关。
# True  = 整个项目完全不加载任何 MCP 服务器（忽略 mcp.yaml 所有配置与各 agent 的 mcp_servers 声明）。
# False = 恢复原有行为。
DISABLE_MCP_GLOBALLY: bool = True
```

## 生效位置

`load_mcp_config()` 入口加了短路：

```python
if DISABLE_MCP_GLOBALLY:
    return {"servers": {}, "defaults": []}
```

调用处共两处，都被截断：
- `src/agents/base.py:150`
- `src/core/mcp_manager.py:331`

## 用法

- **关闭 MCP**（当前默认）：`DISABLE_MCP_GLOBALLY = True`
- **恢复 MCP**：改为 `False`，无需还原 `config/mcp.yaml` 或任何 agent 的 `mcp_servers: [...]` 配置（原配置原样保留，不丢失信息）。

## 为什么这样改

对比其他做法：

| 方式 | 缺点 |
|---|---|
| 清空 `config/mcp.yaml` 的 `servers` + `defaults` | 仍会启动空 MCP 管理器；还得把 9 个 agent config 的 `mcp_servers` 逐个清空，容易漏 |
| 把每个 agent 的 `mcp_servers` 改为 `[]` | 分散在 9 个文件，新加 agent 容易忘 |
| **Python 侧一个常量**（本方案）✅ | 一处决定全局；agent / mcp.yaml 配置原样保留便于将来恢复 |

## 注意事项

- 关闭 MCP **不影响** agent 读写本地文件。读写走的是内置工具（`read_document`、`create_document`、`collect_data`，定义在 `src/tools/FileEdit.py`），与 MCP 无关。
- 关闭后任务管理器里不应再出现 `npx @modelcontextprotocol/...` 子进程。
