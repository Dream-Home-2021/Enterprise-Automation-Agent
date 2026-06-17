# 具备动态情感感知与安全沙箱数据分析能力的 Multi-Agent 系统需求分析说明书 (PRD)

## 1. 项目概述
本规范旨在定义一款打破传统“绝对顺从”设定的新型 AI Agent 系统。该系统具备**独立动态人格**与**硬核数据分析能力**。系统通过多轮交互对用户进行客观行为审计，逐渐形成动态好感度，进而改变自身的情绪状态、对话 tone 调，并拥有**拒绝为低好感度用户工作（罢工）**的自主决策权。同时，在满足工作先决条件时，系统可安全调度本地 Python 沙箱环境进行专业的工作文件数据分析。整个项目生命周期将通过 GitHub 进行敏捷代码管理与版本控制。

---

## 2. 多智能体架构与核心控制流

系统采用基于 LangGraph 的多智能体（Multi-Agent）协同架构，将“情感决策（人设）”与“数据计算（工具）”彻底解耦。

### 2.1 智能体角色定义
* **主管智能体 (Supervisor Agent)：** 系统的总网关。负责解析多用户身份、消费全局状态（State）、驱动情绪评估引擎，执行核心控制流路由。
* **数据执行员 (Data Agent)：** 专业技术人格，不带情绪色彩。仅在通过主管网关的先决条件后被唤醒，通过 MCP（模型上下文协议）标准接口调用本地 Python 隔离沙箱进行数据处理。
* **防御性陪聊员 (Chat Agent)：** 负面情感对齐人格。当主管判定系统处于“罢工”或“冷淡”状态时激活，负责用讽刺、拒绝、或引导用户道歉的语气进行流式对答。

### 2.2 情绪先决条件网关控制律（Gateway Protocol）
执行层 Data Agent 及本地 MCP 专属工具链的触发，**强依赖于 Supervisor Agent 的前置情绪状态评估**。
* **硬性熔断：** 当全局状态中的 `current_emotion == 'strike'` 时，条件路由器必须在控制流层面强制熔断数据分析链路，阻止大模型触碰工具，将句柄移交至 Chat Agent。
* **关系修复死锁避免：** 处于罢工状态时，控制流仅允许向“引导道歉/提供情绪价值”的文本交互节点倾泄，直至用户通过后续真诚沟通使评分回升，方可重新激活工具链。

---

## 3. 多租户身份鉴权与隔离规范

系统初期支持轻量化多租户硬隔离，划分为两个固定账户：`main`（主用户）与 `guest`（访客用户）。

### 3.1 角色属性差异化矩阵

| 用户名 (Username) | 角色定位 (Role) | 初始好感度分值 | 情绪韧性 (Tolerance) | 数据分析权限边界 |
| :--- | :--- | :--- | :--- | :--- |
| **main** | 首席管理员 / 开发者 | 80 分 (正常合作偏信任) | **极高**。偶尔的命令式语气扣分少，加分权重高；享有低分时“抱怨但执行”的**高级豁免权**。 | 拥有本地沙箱完整读写权限，可处理核心敏感资产文件。 |
| **guest** | 临时访客 / 测试员 | 50 分 (冷淡/保持警惕) | **极低**。不礼貌、戏弄或无理请求触发高倍率扣分；一触即发进入罢工状态。 | 仅能处理公开/脱敏数据，禁止触碰底层核心配置。 |

---

## 4. 全局上下文（Global State）与交互中间件规范

### 4.1 全局上下文结构
系统基于 LangGraph 维护一个贯穿生命周期的全局上下文状态机（GlobalAgentState），统一采用 `TypedDict` 进行规约：

```python
class GlobalAgentState(TypedDict):
    username: str                   # 用户唯一标识: 'main' 或 'guest'
    role: str                       # 权限标签: 'admin' 或 'visitor'
    user_metrics: dict              # 四维量化评分: {politeness, trust, rationality, empathy}
    current_emotion: str            # 激活情绪: 'adoration', 'normal', 'cold', 'strike'
    long_term_insights: list        # RAG召回的历史观察日记
    messages: list                  # 经修剪的短期滚动聊天记录
    active_file_path: str           # 当前操作的文件路径
    last_code_generated: str        # MCP沙箱拟执行或已执行的Python代码
    requires_approval: bool         # 高危操作挂起拦截标志
    approval_result: dict           # 中间件返回的审批决策

4.2 交互中间件控制（Human-in-the-Loop）高危动作拦截： 任何涉及本地文件写操作（修改、删除、覆写）的指令，系统严禁直接执行，必须在 Tool 触发阶段调用 LangGraph 原生 interrupt() 强制挂起图流程。标准输入输出 Schema 规范：上下文输出（Agent -> 中间件）： 触发拦截时，系统对外吐出标准 JSON，包含 session_id, user_auth, emotional_state, 以及 high_risk_action.payload（含拟执行代码预览与 Diff 摘要）。审批输入（中间件 -> Agent）： 接收前端用户决策，数据格式必须严格对齐 {"status": "approved/rejected/modified", "user_feedback": "..."} 规范，通过 Resume 通道安全唤醒图状态机。

5. 生产级分层记忆与高级 RAG 检索架构系统放弃传统的“全量聊天记录轰炸”模式，采用一体化 PostgreSQL (PGVector) 分层存储体系。
5.1 短期状态快照（Thread Memory）采用 LangGraph 官方驱动 PostgresSaver 实现。图中每经过一个节点自动进行事务级 Checkpoint 持久化，完美支持高并发下的会话线程安全、状态断点恢复与 Time Travel（时间旅行）回滚调试。
5.2 长期语义记忆 RAG 机制（Cross-thread Memory）异步浓缩管道（Async Pipeline）： 禁止在同步流式对话中写入长期记忆。系统需在会话闲置（5分钟无输入）时异步调度轻量大模型，读取该 Session 的 messages，压缩生成 100 字的《用户客观行为观察日记》，通过 Embedding模型转化为向量追加写入 user_observations 表。带元数据预过滤的混合检索（Hybrid Search with Pre-filtering）： 新会话建立时，系统必须首先执行硬性 SQL 过滤条件 WHERE username = :current_user，在此安全沙箱内，同时启动 PGVector 向量检索（捕捉情感、语气意图）与 TSVector 全文检索（捕捉硬关键词）。精细化重排（Reranking）： 混合检索出的 Top-10 候选日记，必须送入轻量化重排模型（如 bge-reranker）进行交叉编码打分，最终取最优 Top-2 观察日记 注入全局状态，作为情绪初始 Prompt Background。

6. 生产级非功能性与安全性能需求
6.1 流式输出（Streaming）下的内容防线（Guardrails）输入端拦截： 采用高性能 AC 自动机（Aho-Corasick）算法对用户 Prompt 进行毫秒级静态敏感词匹配，涉政涉黄直接熔断并扣分。输出端滑动窗口过滤： 针对大模型 SSE（Server-Sent Events）流式吐字，系统在中间件层维护一个尺寸为 6 个汉字的滚动滑块缓冲区。敏感词匹配在滑块内同步运行。一旦触发违规，在 50ms 内执行 Stream Abort 句柄强行熔断大模型流，并无缝替换为系统情绪化降级文本。
6.2 短期上下文滚动截断（Context Window Truncation）为控制 Token 成本并防止大模型注意力分散，系统在每次呼叫 LLM 节点前执行滚动修剪，默认仅保留最新的 12 条消息（约 3-4 轮完整对话）。首部的 System Prompt 节点、以及激活的实体元数据（active_file_path 等）享有截断豁免权。被切除的历史消息其核心语义已由异步浓缩模块留存至向量库，确保系统不发生“业务失忆”。
6.3 容器化沙箱并发与安全多沙箱隔离： 后端 API（基于 FastAPI 异步 ASGI 架构）在面对并发请求时，必须为每个活跃 Session 调度独立的、相互隔离的 MCP Server / Docker 容器实例。计算配额硬限制： 容器单实例严格限制 CPU $\le$ 0.5核，Memory $\le$ 512MB。代码执行设置硬超时限额 $\le$ 10s，超时自动杀掉（Kill）进程，防止恶意死循环代码拖垮服务器。
6.4 生产级容错与可观测性高可用容错（Fallback）： 核心模型 API 遭遇限流或网络抖动时，系统需配置二级降级图，自动切换至备用本地化开源模型；情绪判定 JSON 解析失败时切换至默认 normal 硬编码状态，保证系统不崩溃。时间消气机制（Time-based Decay）： 每次会话装载时，比对当前时间与用户表最后更新时间。若间隔超 24 小时，量化评分自动向初始均值回弹 10%，模拟人类情感随时间淡化的真实逻辑。链路追踪： 全链路集成追踪工具（如 LangSmith），详尽审计每次会话中 “用户输入 -> 情绪评分变动 -> 动态路由跳转 -> 工具链触发” 的完整决策树，确保线上故障分钟级定位。

7. GitHub 代码管理与项目协同规范为满足生产级的敏捷开发、版本控制与 CI/CD 自动化部署需求，项目必须严格遵循以下 GitHub 研发规范。
7.1 分支策略（Git Flow 简化版）main 分支： 绝对稳定的生产分支。受保护（Protected Branch），严禁直接 Push 提交。所有合入必须通过 Pull Request（PR）并满足至少 1 人的 Code Review 审批。develop 分支： 主开发分支，所有功能分支的集散地。feature/ 分支：* 功能开发分支（例如 feature/rag-memory、feature/mcp-sandbox）。开发完毕后向 develop 提交 PR。
7.2 敏感数据防护与环境变量管理规范（严禁泄露密钥）由于本项目深度结合了大模型 API（OpenAI/Claude/Qwen）与本地 PostgreSQL 凭证，严禁将任何明文密钥、数据库密码、API Key 提交至 GitHub 仓库。.gitignore 严格配置： 仓库根目录必须配置 .gitignore，强制忽略以下文件：Plaintext.env
*.pyc
__pycache__/
/data/
.langgraph/
本地环境配置： 统一使用 .env.example 文件提供非敏感的配置模板。开发者本地复制为 .env 并自行填写密钥。GitHub Secrets 安全托管： 生产环境与测试环境所需的 LLM_API_KEY、POSTGRES_URL 等，必须安全托管在 GitHub 仓库设置的 Settings -> Secrets and variables -> Actions 中。7.3 GitHub Actions 自动化工作流 (CI/CD)项目根目录下需配置 .github/workflows/ci.yml，在每次代码向 develop 或 main 提交 PR 时，自动触发以下流：代码规范检查 (Linting)： 使用 flake8 或 black 自动执行 Python 代码格式化和语法检查。自动化单元测试 (Testing)： 自动拉起测试环境，对 LangGraph 的条件路由（情绪总闸）、JSON 输入输出格式 Schema 进行断言测试。沙箱镜像自动化构建（可选）： 检测到 MCP 模块变更时，自动通过 GitHub Actions 构建最新的 Docker 沙箱镜像并推送到镜像仓库。

8.📁 dynamic-emotional-agent/          # 项目根目录
├── 📁 .github/                      # GitHub 自动化规范目录
│   └── 📁 workflows/
│       └── ci.yml                   # CI/CD 工作流（代码检查、自动化单元测试）
├── .gitignore                       # 严格配置，防止密钥与本地临时数据上传
├── .env.example                     # 环境变量本地配置模板（不含真实密钥）
├── README.md                        # 项目启动与仓库全局说明
├── requirements.txt                 # 项目依赖声明文件
│
├── 📁 src/                          # 核心源代码目录
│   ├── __init__.py
│   ├── main.py                      # FastAPI 异步服务启动入口 (ASGI)
│   │
│   ├── 📁 agents/                   # 多智能体（Multi-Agent）模块
│   │   ├── __init__.py
│   │   ├── state.py                 # 全局上下文 GlobalAgentState (TypedDict 规范)
│   │   ├── supervisor.py            # 主管 Agent (身份识别、情绪网关先决条件、路由决策)
│   │   ├── data_worker.py           # 数据执行员 Agent (专注于驱动 MCP 调用 Pandas)
│   │   ├── chat_defender.py         # 防御性陪聊员 Agent (罢工或冷淡时流式对答)
│   │   └── graph.py                 # LangGraph 图结构组装与编译中心
│   │
│   ├── 📁 storage/                  # 记忆与存储模块
│   │   ├── __init__.py
│   │   ├── connection.py            # PostgreSQL 数据库连接池管理
│   │   ├── checkpointer.py          # PostgresSaver (会话级短期状态快照中心)
│   │   ├── vector_store.py          # PGVector 操作流 (长期日记向量检索与 RAG 匹配)
│   │   └── memory_pipeline.py       # 异步记忆浓缩管道 (异步触发 LLM 生成观察日记)
│   │
│   ├── 📁 mcp/                      # 模型上下文协议与沙箱管理模块
│   │   ├── __init__.py
│   │   ├── server.py                # MCP Server 注册与工具映射 (Function Calling)
│   │   └── client.py                # 触发远端 Docker 沙箱执行 Python 代码的客户端
│   │
│   └── 📁 guardrails/               # 内容防线与安全防护模块
│       ├── __init__.py
│       ├── input_filter.py          # 输入端：高性能 AC 自动机敏感词过滤
│       ├── output_stream_buffer.py  # 输出端：流式滑动窗口（Sliding Window）熔断器
│       └── context_truncator.py     # 消息链滚动截断器 (保留 12 条消息与关键元数据豁免)
│
├── 📁 tests/                        # 自动化测试目录
│   ├── __init__.py
│   ├── test_gateway.py              # 情绪网关总闸/罢工逻辑断言测试
│   ├── test_schema.py               # 中间件输入输出 JSON Schema 规约测试
│   └── test_guardrails.py           # 流式滑动窗口熔断单元测试
│
├── 📁 docker/                       # 容器化沙箱运行配置
│   └── mcp-python-sandbox.Dockerfile # 专用于执行 Pandas 数据分析限制配额的隔离镜像
│
└── 📁 docs/                         # 项目文档目录
    └── PRD_Dynamic_Emotional_Agent.md # 刚才我们生成的生产级需求分析说明书