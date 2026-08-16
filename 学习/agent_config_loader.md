# agent_config_loader.py 全面解读

## 一句话总结

**这个文件是 HR 档案管理员**——不干活，只负责把每个 Agent 的配置文件读出来、解析成 Python 对象，发给需要的地方。

def（函数）	            HR在做啥	                                    谁叫HR做这事

__init__	       HR上班第一天，确认"去哪找员工档案"	              程序启动时自动做
discover_agents	   点名：去办公室逛一圈，看今天谁在岗	                 工厂要创建员工时
load_metadata	    发工牌：只念名字和岗位，不念完整手册	                 内部用
load_system_prompt	发岗位说明书：告诉员工"你是谁、该怎么说话"	            工厂要创建员工时
load_skills	        发培训手册：技能书，需要时才发	                       工作流跑起来后
load_rules	        发员工手册：规章制度	                               拼进岗位说明书
load_mcp_config	    发系统权限：你能用哪些内部系统	                     工作流跑起来后
get_model_config	告诉你用哪个大脑：用 GPT 还是 Claude	                   工厂要创建员工时
get_agent_config_loader	   全公司只有一个HR	                           所有地方都调用这个

---

## 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                   agent_config_loader.py                      │
├─────────────────────────────────────────────────────────────┤
│  1. 数据类定义（第 66-134 行）—— 定义"工牌/技能书/规则"格式   │
│  2. AgentConfigLoader 类（第 137-779 行）—— HR 的具体工作流   │
│  3. 单例函数（第 782-804 行）—— 全公司只有一个 HR              │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心设计理念：渐进式披露

LLM 的上下文窗口有限，一次塞太多内容会"记不住"。所以分三级加载：

| 层级 | 加载时机 | 内容 | 类比 |
|------|----------|------|------|
| L1 元数据 | 始终加载 | 名字、版本、模型 | 看工牌确认是谁 |
| L2 指令 | Agent 触发时 | 完整提示词 + 规则 + 技能摘要 | 发岗位说明书 |
| L3 资源 | 按需加载 | 技能书全文、MCP 配置、规则全文 | 需要时才查培训材料 |

---

## 数据类（3 个容器）

### AgentMetadata —— 工牌

```python
@dataclass
class AgentMetadata:
    name: str                    # 如 "code_agent"
    description: str             # 一句话描述
    version: str                 # 版本号
    model: Dict[str, Any]        # 用哪个大脑，如 {"provider": "openai", "model": "gpt-4"}
    skills: List[str]            # 需要哪些技能书
    tools: List[str]             # 可用工具列表
    rules: Any                   # 规则文件路径
    mcp_servers: List[str]       # 能连哪些内部系统
    use_complete_prompt: bool    # 是否把 markdown 当完整提示词
```

### SkillConfig —— 技能书

```python
@dataclass
class SkillConfig:
    name: str           # 如 "code_search"
    description: str    # 一句话描述
    content: str        # SKILL.md 完整内容
    path: Path          # 文件绝对路径
```

### RuleConfig —— 规章制度

```python
@dataclass
class RuleConfig:
    trigger: str                  # 何时生效：always_on / on_demand / context_match
    priority: int                 # 值越大越先应用
    context_patterns: List[str]   # 上下文匹配模式
    content: str                  # 规则正文
    path: Optional[Path]          # 文件路径
```

---

## 关键方法速查

| 方法 | 层级 | 作用 | 返回值 |
|------|------|------|--------|
| `discover_agents()` | L1 | 扫描目录，看有哪些 Agent | `List[str]` |
| `load_metadata()` | L1 | 读 YAML frontmatter | `AgentMetadata` |
| `load_system_prompt()` | L2 | 读提示词 + 拼规则 + 拼技能摘要 | `str` |
| `load_skills()` | L3 | 加载技能书全文 | `List[SkillConfig]` |
| `load_rules()` | L3 | 加载规则全文 | `List[RuleConfig]` |
| `load_mcp_config()` | L3 | 加载 MCP 服务器配置 | `Dict` |
| `get_model_config()` | L1 | 获取模型配置 | `Dict` |

---

## 方法详解

### discover_agents() —— 点名

扫描 `config/agents/` 目录，找有 `AGENT.md` 的子目录，跳过 `_` 开头的隐藏目录。

```
agents/
├── process_agent/AGENT.md  ✅
├── code_agent/AGENT.md     ✅
└── _hidden/AGENT.md        ❌ 跳过
返回: ["process_agent", "code_agent"]
```

### load_metadata() —— 发工牌

1. 读 `config/agents/<name>/AGENT.md`
2. 用正则提取 `---` 之间的 YAML frontmatter
3. 再读同目录下的 `config.yaml` 获取 skills/rules/mcp_servers
4. 缓存结果，下次不重复读

### load_system_prompt() —— 发岗位说明书

1. 读 AGENT.md，去掉 frontmatter，取正文
2. 加载 `trigger=always_on` 的规则，拼到末尾
3. 加载技能书，**只取名字和描述**（省空间），拼到末尾
4. 如果 `use_complete_prompt=True`，加 `SYSTEM_PROMPT:` 前缀

### load_skills() —— 按清单取书

1. 从 metadata 拿到技能名列表
2. 去 `config/skills/<name>/SKILL.md` 逐个找
3. 找到就放进列表，找不到就记警告

### load_rules() —— 加载规则

1. 从 metadata 拿到规则路径列表
2. `_` 开头的路径从 `config/` 开始找（共享规则）
3. 其他路径从 Agent 自己目录开始找
4. 按优先级降序排列（值大的先应用）

### load_mcp_config() —— 发系统权限

1. 首次调用时读 `config/mcp.yaml` 并缓存
2. 合并默认服务器 + Agent 特定服务器（取并集）
3. 只返回启用的服务器配置

---

## 私有方法（内部工具）

| 方法 | 作用 |
|------|------|
| `_extract_frontmatter()` | 用正则提取 `---` 之间的 YAML |
| `_parse_skill_file()` | 解析单个 SKILL.md 为 SkillConfig |
| `_parse_rule_file()` | 解析单个规则文件为 RuleConfig |
| `_load_rules_content()` | 只取 always_on 规则，拼成字符串 |
| `_load_skills_content()` | 只取技能名字+描述，拼成字符串 |
| `_load_mcp_config_file()` | 读 mcp.yaml，展开环境变量 |
| `_expand_env_vars()` | 递归展开 `${VAR_NAME}` 语法 |
| `_load_per_agent_config()` | 读 Agent 自己的 config.yaml |
| `_get_agent_extended_config()` | 包装器，目前直接调用上面那个 |

---

## 路径关系图

```
config/
├── agents/                    ← config_root
│   ├── code_agent/
│   │   ├── AGENT.md           ← 提示词 + frontmatter
│   │   ├── config.yaml        ← skills/rules/mcp 声明
│   │   └── rules/             ← Agent 私有规则
│   └── _shared/
│       └── rules.md           ← 共享规则（_ 开头）
├── skills/                    ← config_root.parent / "skills"
│   ├── code_search/
│   │   └── SKILL.md           ← 技能书
│   └── git_ops/
│       └── SKILL.md
└── mcp.yaml                   ← MCP 服务器配置
```

---

## 单例模式

```python
_default_loader: Optional[AgentConfigLoader] = None

def get_agent_config_loader() -> AgentConfigLoader:
    global _default_loader
    if _default_loader is None:
        _default_loader = AgentConfigLoader()
    return _default_loader
```

整个程序只创建一个 loader 实例，避免重复创建和浪费内存。所有调用方通过这个函数获取实例。

---

## 与其他文件的协作

| 谁调用了它 | 用来做什么 |
|-----------|-----------|
| `src/agents/factory.py` | 创建 Agent 时加载提示词和模型配置 |
| `src/core/workflow.py` | 工作流启动时加载技能和 MCP 配置 |
| `src/core/schemas.py` | 引用 AgentMetadata 等数据类 |

---

## 正则表达式详解

```python
FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL
)
```

| 符号 | 含义 |
|------|------|
| `^---` | 必须以 `---` 开头 |
| `\s*` | 后面可以有/没有空格 |
| `\n` | 换行 |
| `(.*?)` | 提取目标（非贪婪，尽可能少抓） |
| `\n---` | 遇到 `---` 就停 |
| `re.DOTALL` | 让 `.` 能匹配换行（处理多行 YAML） |

作用：把 `---` 和 `---` 之间的 YAML 抠出来。

---

## 环境变量展开

`_expand_env_vars()` 支持在 YAML 里写 `${DB_PASSWORD}`，程序运行时自动替换成系统环境变量值。递归处理 dict/list/str 三种类型。

---

## 常见疑问

**Q: 为什么要分 L1/L2/L3？**
A: LLM 上下文窗口有限。L1 最轻，L2 创建时必须，L3 需要时才加载。

**Q: Skills 和 Rules 有什么区别？**
A: Skills 是"技能培训手册"（怎么做），Rules 是"规章制度"（必须做/不能做）。

**Q: 这个文件一般需要改吗？**
A: 一般不改。要改 Agent 行为去改 `config/agents/` 下的配置。这个 loader 是基础设施。
