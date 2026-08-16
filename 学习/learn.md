环境篇

docker 1.hub无法拉取项目
       2.pgadmin4 链接pos数据库失败

项目 1.搭建基础框架，测试前后端连通，api环境
     2.技术架构选择，zaamd项目api和数据库等架构收集
     3.初步搭建第一个agent聊天客服
             ---1.数据库token权限不足，申请新权限
             ---2.测试用例通过，实际报错403，忘记导入env。
             ---3.未赋予agent修改数据的工具，出现报错   未解决
             ---4.核对数据库和请求，发现上下文遗忘问题，还有比如创建工单问题，必须参数说  完才能成功创建，缺失就报错。换行就遗忘。  未解决：就是每次传参没有带着上下文
             ---5.用户权限未明确，用户有太大权限
             ---6.回答重复2次
             ---7.1个函数2个命令报错，3号工单状态改为处理中，优先级为高
             ---8.anysc的运行观测？ 目前只作用于函数内，没有并发
                                   @tool
                            async def list_tickets(query: str = "") -> str:
                            """列出或搜索工单。当 query 为空时返回所有工单列表；传入关键词时按关键词搜索工单。
                            返回工单编号、标题、状态。"""
                            if query.strip():
                                   results = await zammad_client.search_tickets(query)
                            else:
                                   results = await zammad_client.list_tickets()

         ------9.rag是个大重点






新建文件（10个）
文件	用途
agent/db/__init__.py	DB 模块入口
agent/db/redis.py	Redis 连接工厂（单例）
agent/db/postgres.py	5 张表 DDL + 完整 CRUD
agent/memory/__init__.py	Memory 模块入口
agent/memory/short_term.py	RedisSaver 检查点工厂
agent/memory/long_term.py	长期记忆读写 + 画像格式化
agent/memory/extract.py	LLM 偏好提取、摘要生成、画像合并
agent/memory/session.py	会话 CRUD + LLM 自动标题生成
agent/memory/history.py	从检查点恢复对话历史
agent/memory/profile.py	画像构建器 + 向量化存储
修改文件（5个）
文件	变更内容
agent/supervisor/graph.py	async 节点、从 config 读 user_id、注入画像到 system prompt
agent/agents/chat_agent.py	call_chat_agent 用 get_config() 传播 config 到子图
agent/service.py	接收 session_id/user_id 构造 config 传参
utils/web_ui.py	完整重写为左侧会话列表 + 右侧聊天区
main/app.py	启动时 init_db + 关闭时清理连接池
.env	新增 AGENT_REDIS_URL、AGENT_DATABASE_URL
requirements.txt	补充 redis、asyncpg、pgvector、orjson 依赖
架构流程

Gradio UI (多会话侧边栏)
  │ session_id, user_id
  ▼
Service Layer → config={"configurable": {"thread_id": session_id, "user_id": 1}}
  │ config 传给 astream()
  ▼
Supervisor Graph (RedisSaver checkpointer)
  │ async supervisor() 从 config 取 user_id → load_profile_inject() → 注入 system prompt
  │ call_chat_agent 内 get_config() 获取 config → 传给子图
  ▼
Chat Agent Graph (RedisSaver checkpointer, 共享 thread_id)
  │ 工具调用自动在同一个检查点线程下
  ▼
Memory Layer
  ├── 短期: RedisSaver 检查点（对话历史自动保存）
  ├── 非语义: PostgreSQL (preferences + summaries + profile)
  └── 语义: PGVector (对话片段向量化)
下次运行前的准备
确保 PostgreSQL 有 agent_memory 数据库和 agent 用户
确保 Redis 在 localhost:6379 运行
运行 python main/app.py（用 langgraph 环境的 Python）

