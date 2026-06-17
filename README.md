# Dynamic Emotional Agent System

> 具备**动态情感感知**与**安全沙箱数据分析能力**的 Multi-Agent 系统

## 系统概述

本系统打破了传统 AI Agent "绝对顺从"的设定，实现了：

- **独立动态人格** — 基于四维量化评分（礼貌度、信任度、理性度、共情度）的实时情绪引擎
- **情绪网关熔断** — 低好感度用户触发罢工机制，拒绝数据分析工作
- **安全沙箱执行** — 通过 MCP 协议隔离 Docker 容器运行 Python 数据分析
- **分层记忆 RAG** — PGVector 向量检索 + TSVector 全文检索 + Reranker 精排
- **内容安全防线** — AC 自动机输入过滤 + 流式滑动窗口输出熔断
- **多租户硬隔离** — main (管理员) / guest (访客) 双角色差异化权限

## 架构

```
User Input
    │
    ▼
┌─────────────────────────────────────────────┐
│              Guardrails (Input Filter)        │
└──────────────────────┬──────────────────────┘
                       ▼
┌─────────────────────────────────────────────┐
│           Supervisor Agent (情绪网关)         │
│   ┌─────────────────────────────────────┐   │
│   │  Emotion Engine → Route Decision     │   │
│   └──────────┬───────────────┬──────────┘   │
└──────────────┼───────────────┼──────────────┘
          ✅ Normal+     ❄️ Cold/Strike
               ▼               ▼
┌──────────────────┐  ┌──────────────────────┐
│   Data Agent     │  │   Chat Defender      │
│  (MCP Sandbox)   │  │  (讽刺/冷淡/引导道歉) │
└──────────────────┘  └──────────────────────┘
```

## 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/dynamic-emotional-agent.git
cd dynamic-emotional-agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

### 2. 启动 PostgreSQL + PGVector

```bash
docker run -d \
  --name emotional-agent-db \
  -e POSTGRES_DB=emotional_agent \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 3. 启动服务

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. API 接口

```bash
# 发送消息（流式 SSE）
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"username": "main", "message": "帮我分析一下 sales.csv"}'
```

## 项目结构

```
dynamic-emotional-agent/
├── .github/workflows/ci.yml   # CI/CD 工作流
├── src/
│   ├── main.py                # FastAPI 启动入口
│   ├── agents/                # 多智能体模块
│   │   ├── state.py           # GlobalAgentState
│   │   ├── supervisor.py      # 主管 Agent（情绪网关）
│   │   ├── data_worker.py     # 数据执行员 Agent
│   │   ├── chat_defender.py   # 防御性陪聊员 Agent
│   │   └── graph.py           # LangGraph 图组装
│   ├── storage/               # 存储模块
│   │   ├── connection.py      # 数据库连接池
│   │   ├── checkpointer.py    # 短期状态快照
│   │   ├── vector_store.py    # PGVector 向量检索
│   │   └── memory_pipeline.py # 异步记忆浓缩
│   ├── mcp/                   # MCP 沙箱模块
│   │   ├── server.py          # MCP Server
│   │   └── client.py          # Docker 沙箱客户端
│   └── guardrails/            # 安全防护模块
│       ├── input_filter.py    # AC 自动机输入过滤
│       ├── output_stream_buffer.py # 流式输出熔断
│       └── context_truncator.py    # 消息链截断
├── tests/                     # 自动化测试
├── docker/                    # Docker 沙箱镜像
└── docs/                      # 项目文档
```

## 用户角色说明

| 用户 | 角色 | 初始好感度 | 情绪韧性 | 数据权限 |
|------|------|-----------|---------|---------|
| `main` | 管理员 | 80 | 极高 | 完整读写 |
| `guest` | 访客 | 50 | 极低 | 仅公开数据 |

## 开发规范

- **分支策略**：`main`(生产) → `develop`(开发) → `feature/*`(功能)
- **敏感数据**：所有密钥通过 GitHub Secrets 管理，严禁明文提交
- **CI/CD**：PR 自动触发 flake8 + black 检查 + pytest 单元测试

## License

MIT
