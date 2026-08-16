# asyncio 与 main.py 学习笔记

## 事件循环（Event Loop）

事件循环是 asyncio 的核心，像一个**调度员**——负责管理和执行所有异步任务。

```python
# 普通脚本通常这样用
async def main():
    await some_async_task()

asyncio.run(main())   # 自动创建循环、运行、关闭
```

`asyncio.run()` 内部会自动创建并设置事件循环，手动 `new_event_loop` + `set_event_loop` 是多余的。

### 什么时候需要手动创建？

1. **Jupyter Notebook** — 已经有一个循环在跑
2. **多线程** — 每个线程需要自己的事件循环
3. **GUI / Web 框架** — 需要长期运行的循环
4. **测试** — 需要精细控制循环生命周期

## main.py 的线程模型

```
主线程（自带事件循环）
  │   跑 main() → MultiAgentSystem().run()
  │
  └── 后台线程 (daemon thread)
         │   跑 loop.run_forever()
         │   专门维持 MCP 长连接
```

一共 **2 个线程**。

### 为什么需要后台线程？

MCP 连接是**长连接**，需要一直"活着"等服务器消息。如果放在主线程：

```python
loop.run_forever()    # 永远不返回
system = MultiAgentSystem()  # 永远执行不到
```

所以必须扔到后台线程，主线程继续干正事。

## 线程 vs 事件循环

- **线程** = 一个独立的工作空间（舞台）
- **事件循环** = 导演，负责调度演员（函数）上台表演

没有舞台，导演没地方导戏。
没有导演，舞台上一片空白。

```python
# 造调度器（不是线程！）
mcp_loop = asyncio.new_event_loop()

# 造线程
mcp_thread = threading.Thread(target=run_mcp_loop, args=(mcp_loop,), daemon=True)
```

**每个线程默认没有事件循环**，Python 只在主线程自动给一个。

## 为什么用异步？

因为 **MCP 的库本身就是异步的**（`async def`），没得选。

```python
# 同步函数放线程里 —— 不需要 asyncio
def sync(): ...
threading.Thread(target=sync).start()

# 异步函数 —— 需要事件循环
async def async_func(): ...
loop = asyncio.new_event_loop()
```

## 同步代码调度异步调用

主线程是同步的，调用异步函数时，把任务扔给后台循环：

```python
asyncio.run_coroutine_threadsafe(
    mcp_tools._arun("搜索"),   # 异步任务
    manager._main_loop          # 扔给后台循环
).result(timeout=120)           # 等结果
```

类比：同步代码自己不跑异步函数，而是"委托"给后台的事件循环去跑。

## try / finally 清理

```python
try:
    system = MultiAgentSystem()
    system.run(user_input)
finally:
    if mcp_loop.is_running():
        mcp_loop.call_soon_threadsafe(mcp_loop.stop)  # 停掉后台循环
    mcp_thread.join(timeout=2)                       # 等线程结束
```

不管成功还是报错，finally 都会执行——优雅退出，释放资源。

## sys.path.insert

```python
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
```

- `__file__` = 当前文件路径（如 `D:/GameDownload/DATAGEN/main.py`）
- `dirname(__file__)` = 文件夹部分（如 `D:/GameDownload/DATAGEN`）
- `sys.path.insert(0, ...)` = 插到模块搜索路径最前面

**把当前脚本所在的目录加到 Python 的模块搜索路径里**，让跨目录导入能正常工作。

## 一次性任务 vs 服务

```python
# 一次性任务 —— 跑完就停
system = MultiAgentSystem()
system.run(user_input)

# 服务 —— 一直跑
while True:
    user_input = input(">> ")
    system.run(user_input)
```

main.py 是批处理（跑一次），不是服务（一直跑），所以不需要循环。

## 什么时候需要异步？

| 场景 | 需要异步吗 |
|------|-----------|
| 网络 IO（HTTP、数据库） | ✅ |
| 文件 IO | ✅ |
| 高并发（Web 服务器） | ✅ |
| 长连接 / 实时推送 | ✅ |
| 定时任务 | ✅ |
| CPU 密集（计算、加密） | ❌ |
| 简单脚本 | ❌ |
| CLI 工具 | ❌ |

**有"等"的地方，才适合异步。**
