# Enterprise Automation Agent
## 项目概述

Enterprise Automation Agent 是一个面向企业场景的 AI 智能体平台，支持两种工作模式：

| 模式 | 触发条件 | 描述 |
|------|----------|------|
| **Chat 模式** | 业务流程问题（创建/查询/更新） | 连接 Zammad 系统，自然语言自动处理业务流程（API 驱动模式 ）|
| **Analysis 模式** | 数据分析/研究类问题 | 启动多 Agent 研究流水线，自动生成报告 |

---

## 核心功能

### 双模式智能路由
- **Main Router** 自动识别用户意图，路由到 Chat 子图或 Analysis 子图
- 两个子图共享同一 Redis 检查点，状态可跨重启持久化

### 多层记忆系统
- **短期记忆**：Redis 持久化 LangGraph checkpoint，支持跨会话恢复
- **长期记忆**：语义记忆和非语义记忆，PostgreSQL + pgvector，自动提取用户偏好和对话摘要，支持Agent节点执行步骤的中断和精确恢复。
- **用户画像**：后台异步提取，形成结构化用户偏好 JSON

### 多Agent协作
- 假设生成、流程规划、可视化、搜索、代码生成、报告、质检、笔记、精炼、聊天

### MCP 协议支持
- 文件系统访问、Web 搜索、GitHub 仓库接入（通过 Model Context Protocol）

### LangSmith 可观测性
- 完整链路追踪，支持 LangGraph Studio 可视化调试

### SSE 实时流式输出
- Server-Sent Events 将 AI 回复逐 token 推送到前端，无需轮询

---

## 系统架构

```
用户请求 (HTTP/SSE)
       │
       ▼
  FastAPI 服务层 (main/app_html.py)
       │
       ▼
  MultiAgentSystem (agent/src/system.py)
       │
       ▼
  ┌─── LangGraph 父图 ──────────────────────┐
  │                                          │
  │  Main Router ──→ Chat 子图               │
  │             └──→ Analysis 子图           │
  │                                          │
  │  Analysis 子图:                          │
  │  Hypothesis → HumanChoice               │
  │      ↓                                   │
  │  Process → Coder/Search/Viz/Report      │
  │      ↓                                   │
  │  QualityReview → NoteTaker              │
  │      ↓                                   │
  │  Refiner → HumanReview → END            │
  └──────────────────────────────────────────┘
       │
       ▼
  记忆层:
  ├── Redis (短期/checkpoint)
  └── PostgreSQL + pgvector (长期记忆/画像/向量)
```

---

## 智能体说明

### 分析子图 Agents

| Agent | 职责 |
|-------|------|
| **Hypothesis Agent** | 根据用户问题生成研究假设，确定研究方向 |
| **Process Agent** | 任务拆解与调度，决定下一步调用哪个 Agent |
| **Search Agent** | Google 搜索 + 网页抓取（Selenium + FireCrawl/CRW） |
| **Code Agent** | Python 代码生成与执行，数据处理脚本 |
| **Visualization Agent** | 图表生成，数据可视化 |
| **Report Agent** | 汇总所有产物，生成 Markdown 研究报告 |
| **Quality Review Agent** | 质量审核，不合格则触发返工循环 |
| **Note Agent** | 记录每轮任务完成情况，推进 todo_list |
| **Refiner Agent** | 根据质检反馈精炼报告 |

### 聊天子图 Agents

| Agent | 职责 |
|-------|------|
| **Chat Agent** | Zammad系统操作（列表/查询/创建/更新）+ 用户搜索 |

### 后台 Agents

| Agent | 职责 |
|-------|------|
| **Profile Extract Agent** | 从对话中提取用户偏好（低温度，一致性优先） |
| **Session Title Agent** | 自动生成会话标题 |

---

## 记忆系统

### 短期记忆（Redis）
- 基于 `AsyncRedisSaver` 的 LangGraph checkpoint
- **断点续传与 Token 节省**：利用 Redis 精准记录细粒度至 Agent 内部执行步骤（如大模型思考、工具调用等）的检查点，使长业务流程在中断后能无缝接续，避免重复计算从而极大节省昂贵的 Token 消耗。
- 每条消息后自动保存历史记录与状态，进程崩溃后可精准恢复（默认 `6380` 端口）。

### 长期记忆（PostgreSQL + pgvector）

```
agent_sessions               # 会话元数据
agent_user_preferences       # 结构化用户偏好（key-value + confidence）
agent_conversation_summaries # 对话摘要（带 tags）
agent_user_profile           # 聚合用户画像（JSONB）
agent_memory_vectors         # 向量语义记忆（pgvector）
```

- 后台每 `MEMORY_BATCH_INTERVAL_MINUTES` 分钟自动触发提取
- 支持向量相似度检索（Top-K 语义记忆召回）

### 人机交互（LangGraph interrupt）

```
graph 执行 → 到达 HumanChoice 节点 → interrupt() 暂停
       ↓
前端收到 SSE 中断事件 → 显示选项对话框
       ↓
用户选择 → POST /api/resume → Command(resume=data) → 继续执行
```

---

## 工具生态

### 内置工具

| 工具 | 位置 | 功能 |
|------|------|------|
| `google_search` | `agent/src/tools/internet.py` | Selenium 驱动 Google 搜索 |
| `scrape_webpages` | `agent/src/tools/internet.py` | 网页抓取（WebBaseLoader/FireCrawl/CRW）|
| `file_edit` | `agent/src/tools/file_edit.py` | 文件读写操作 |
| `security` | `agent/src/tools/security.py` | 安全校验工具 |
| `skills` | `agent/src/tools/skills.py` | Agent 技能注册 |

### Zammad 工单工具

| 工具 | 功能 |
|------|------|
| `list_tickets` | 列出工单列表 |
| `get_ticket` | 查询工单详情 |
| `create_ticket` | 创建新工单 |
| `update_ticket` | 更新工单状态/内容 |
| `search_users` | 搜索 Zammad 用户 |
| `get_user` | 获取用户详情 |

### MCP 工具（Model Context Protocol）

| 服务 | 能力 |
|------|------|
| `filesystem` | 访问工作目录下的数据文件 |
| `web-search` | Tavily 网页搜索 |
| `github` | GitHub 仓库读写 |


## 目录结构

```
.
├── agent/                           # 核心 Agent 包
│   ├── api/
│   │   └── zammad_client.py         # Zammad REST API 客户端
│   ├── db/
│   │   ├── init.sql                 # 数据库初始化（PostgreSQL）
│   │   ├── postgres.py              # asyncpg 连接池管理
│   │   └── redis.py                 # aioredis 连接管理
│   ├── memory/
│   │   ├── extract.py               # LLM 驱动的偏好提取 & 摘要生成
│   │   ├── history.py               # 对话历史加载 & checkpoint 管理
│   │   ├── long_term.py             # 长期记忆查询接口
│   │   ├── profile.py               # 用户画像管理 + 后台提取器
│   │   ├── session.py               # 会话 CRUD（PostgreSQL）
│   │   └── short_term.py            # AsyncRedisSaver 初始化
│   └── src/
│       ├── agents/                  # 各专业 Agent 实现
│       │   ├── base.py              # BaseAgent 基类
│       │   ├── chat_agent.py        # Zammad 工单 Agent
│       │   ├── hypothesis_agent.py  # 研究假设 Agent
│       │   ├── process_agent.py     # 流程规划 Agent
│       │   ├── search_agent.py      # 搜索 Agent
│       │   ├── code_agent.py        # 代码生成 Agent
│       │   ├── visualization_agent.py # 可视化 Agent
│       │   ├── report_agent.py      # 报告生成 Agent
│       │   ├── quality_review_agent.py # 质检 Agent
│       │   ├── note_agent.py        # 笔记 Agent
│       │   ├── refiner_agent.py     # 精炼 Agent
│       │   └── factory.py           # AgentFactory（按名字创建 Agent）
│       ├── core/
│       │   ├── state.py             # 共享 State（Pydantic BaseModel）
│       │   ├── workflow.py          # WorkflowManager（父图 + 子图构建）
│       │   ├── workflow_router.py   # 路由决策函数
│       │   ├── node.py              # LangGraph 节点执行层
│       │   ├── api_routes.py        # FastAPI 路由（REST + SSE）
│       │   ├── agent_config_loader.py # Agent YAML 配置加载
│       │   ├── mcp_manager.py       # MCP 工具管理器
│       │   └── language_models.py   # LLM 供应商管理
│       ├── llm/                     # LLM 供应商适配层
│       │   ├── factory.py           # ProviderFactory
│       │   ├── openai.py            # OpenAI
│       │   ├── anthropic.py         # Anthropic
│       │   ├── google.py            # Google Gemini
│       │   ├── openrouter.py        # OpenRouter（多模型聚合）
│       │   ├── groq.py              # Groq
│       │   ├── ollama.py            # Ollama（本地模型）
│       │   └── azure.py             # Azure OpenAI
│       ├── tools/                   # 工具层
│       │   ├── internet.py          # Google 搜索 + 网页抓取
│       │   ├── file_edit.py         # 文件操作
│       │   ├── mcp_tools.py         # MCP 协议工具
│       │   ├── security.py          # 安全校验
│       │   ├── tool_config.py       # 工具配置管理
│       │   └── validators.py        # 参数校验
│       ├── config.py                # 全局配置（环境变量 + YAML）
│       ├── logger.py                # 日志工具
│       └── system.py                # MultiAgentSystem 门面类
│
├── config/                          # 配置文件目录
│   ├── agent_models.yaml            # 每个 Agent 的 LLM 模型配置
│   ├── mcp.yaml                     # MCP 工具服务配置
│   ├── tool_limits.yaml             # 工具调用限制配置
│   └── agents/                      # 各 Agent 专属 Prompt 配置
│
├── frontend/                        # Vue 3 前端
│   └── src/
│       ├── components/              # UI 组件（ChatView, MessageList 等）
│       ├── composables/             # 组合式 API（useChatStream）
│       ├── stores/                  # Pinia 状态管理
│       └── api/                     # HTTP 客户端封装
│
├── main/
│   └── app_html.py                  # FastAPI 应用入口
│
├── tools/
│   └── chat/                        # Zammad 工单工具
│       ├── ticket.py                # 工单 CRUD
│       └── user.py                  # 用户查询
│
├── utils/
│   ├── log.py                       # 统一日志工具
│   └── agent_log.py                 # 请求生命周期日志
│
├── tests/                           # 测试套件
├── agent-docker-compose.yml         # PostgreSQL + Redis 容器配置
├── langgraph.json                   # LangGraph Studio 配置
├── studio_entry.py                  # LangGraph Studio 入口
├── requirements.txt                 # Python 依赖
└── .env.example                     # 环境变量模板
```

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/Dream-Home-2021/Enterprise-Automation-Agent.git
cd Enterprise-Automation-Agent
git checkout core
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入所需的 API Key 和配置
```

### 3. 启动数据库服务

```bash
# 启动 PostgreSQL（端口 5433）+ Redis（端口 6380）
docker compose -f agent-docker-compose.yml up -d

# 确认服务健康
docker compose -f agent-docker-compose.yml ps
```

### 4. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 5. 构建前端（可选）

```bash
cd frontend
npm install
npm run build
cd ..
```

### 6. 启动服务

```bash
python main/app_html.py
```

服务默认运行在 `http://localhost:7860`，前端界面访问该地址即可。

---

## 环境变量配置

复制 `.env.example` 为 `.env` 并填写以下配置：

```env
# ===== LLM API Keys =====
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1

# 嵌入模型（用于向量存储）
EMBEDDING_MODEL=text-embedding-ada-002

# ===== PostgreSQL + pgvector =====
AGENT_DATABASE_URL=postgresql://agent:agent@localhost:5433/agent_memory
AGENT_DB_POOL_SIZE=10

# ===== Redis（短期记忆/checkpoint）=====
REDIS_URL=redis://localhost:6380

# ===== 长期记忆提取 =====
MEMORY_EXTRACT_MODEL=gpt-4o-mini
MEMORY_EXTRACT_INTERVAL=5
MEMORY_BATCH_INTERVAL_MINUTES=10
MEMORY_VECTOR_TOP_K=5

# ===== LangSmith（可观测性）=====
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=enterprise-automation-agent

# ===== Zammad =====
ZAMMAD_URL=http://your-zammad-host
ZAMMAD_TOKEN=your-token

# ===== 网页抓取 =====
FIRECRAWL_API_KEY=fc-...
CRW_API_KEY=crw-...
CRW_API_URL=https://fastcrw.com/api

# ===== MCP 工具 =====
TAVILY_API_KEY=tvly-...
GITHUB_TOKEN=ghp_...

# ===== 应用配置 =====
APP_HOST=localhost
APP_PORT=7860
AGENT_USER_ID=1
WORKING_DIRECTORY=./data
CONDA_ENV=base
CHROMEDRIVER_PATH=./chromedriver/chromedriver
```

---

## 模型配置

编辑 `config/agent_models.yaml` 为每个 Agent 指定 LLM 模型：

```yaml
agents:
  chat_agent:
    provider: openrouter       # openai / anthropic / google / openrouter / groq / ollama / azure
    model_config:
      model: nvidia/nemotron-3-super-120b-a12b:free
      temperature: 1.0
    max_iterations: 15

  hypothesis_agent:
    provider: openrouter
    model_config:
      model: google/gemini-2.5-pro
      temperature: 1.0
    max_iterations: 15
  # ... 其余 Agent 类似配置
```

**支持的 LLM 供应商：**

| 供应商 | 说明 |
|--------|------|
| `openai` | OpenAI GPT 系列 |
| `anthropic` | Claude 系列 |
| `google` | Gemini 系列 |
| `openrouter` | 聚合多家模型 |
| `groq` | 高速推理 |
| `ollama` | 本地部署模型 |
| `azure` | Azure OpenAI |

---

## MCP 工具配置

编辑 `config/mcp.yaml` 配置 MCP 工具服务：

```yaml
servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "${WORKING_DIRECTORY}"]

  web-search:
    command: npx
    args: ["-y", "@anthropic/mcp-server-web-search"]
    env:
      TAVILY_API_KEY: ${TAVILY_API_KEY}

  github:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_TOKEN}

defaults:
  - filesystem   # 所有 Agent 默认启用的 MCP 工具
```

---

## API 接口

服务启动后，API 文档访问：`http://localhost:7860/docs`

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/api/chat` | 发送消息（SSE 流式响应） |
| `POST` | `/api/resume` | 恢复 interrupt 暂停的对话 |
| `GET` | `/api/sessions` | 获取会话列表 |
| `POST` | `/api/sessions` | 创建新会话 |
| `DELETE` | `/api/sessions/{id}` | 删除会话 |
| `GET` | `/api/sessions/{id}/history` | 获取会话历史 |

**SSE 响应格式：**

```
data: {"type": "token", "content": "..."}
data: {"type": "interrupt", "value": {...}}
data: {"type": "done"}
```

---

## 前端使用

前端基于 **Vue 3 + TypeScript + Vite** 构建，提供：

- 📝 多会话管理侧边栏
- 💬 流式聊天界面（SSE 实时展示）
- 🤔 Human Choice 对话框（研究假设确认）
- 📎 附件上传支持

**开发模式：**

```bash
cd frontend
npm install
npm run dev
```

**生产构建：**

```bash
npm run build   # 构建到 frontend/dist/
```

> 构建产物会被 FastAPI 自动挂载，无需额外部署。

---

## LangGraph Studio

项目支持 LangGraph Studio 可视化调试：

```bash
pip install langgraph-cli
langgraph dev
```

访问 Studio 后选择 `enterprise_automation_agent` 图，可以：
- 可视化查看 Agent 执行流程
- 实时观察 State 变化
- 手动触发 interrupt 恢复

---

## 分支策略

| 分支 | 说明 |
|------|------|
| `main` | 生产环境，始终可运行 |
| `core` | 主开发分支，集成 LangSmith + 导入流程 |
| `feature/*` | 每个新功能独立分支 |
| `agent-core` | Agent 核心架构分支 |

**开发规则：**
1. `main` 分支始终保持可运行状态
2. 每个功能 = 一个 `feature/*` 分支
3. LangGraph 节点独立开发（agent / tools / memory / router）
4. Tool Calling 封装独立，不侵入 Agent 核心
5. 所有变更必须可逆（干净的 commit + 合并前可运行）

---

## 致谢

本项目的核心研究流水线架构（Hypothesis → Process → Search/Code/Visualization → Report → QualityReview 工作流）深受 [**DATAGEN**](https://github.com/zi-yue-1129/DATAGEN) 项目的启发。

> **DATAGEN** — *AI-driven multi-agent research assistant automating hypothesis generation, data analysis, and report writing.*
>
> 作者：[@zi-yue-1129](https://github.com/zi-yue-1129)
> 仓库：[https://github.com/zi-yue-1129/DATAGEN](https://github.com/zi-yue-1129/DATAGEN)

DATAGEN 提供了多智能体协同研究自动化的设计范式，本项目在此基础上进行了以下扩展：

- 集成 **Zammad 工单管理**，支持 Chat 与 Analysis 双模式路由
- 引入 **Redis + PostgreSQL 双层记忆系统**，实现跨会话状态持久化，支持Agent节点执行步骤的中断和任意恢复。
- 增加 **LangGraph interrupt()** 人机协作机制
- 添加 **Vue 3 前端**与 **SSE 流式推送**
- 接入 **MCP 协议**工具生态与 **LangSmith** 可观测性

感谢 DATAGEN 的作者和贡献者们的开创性工作 🙏

---

## 许可证

MIT License

---
