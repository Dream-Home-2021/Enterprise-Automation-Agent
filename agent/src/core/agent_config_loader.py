# ============================================================================
# agent_config_loader.py — Agent 配置加载器（渐进式披露）
# ============================================================================
# 文件角色：
#   本项目中所有 Agent（智能体）的"性格/人设/工具"都存储在 Markdown 文件里。
#   本文件负责把这些 Markdown 文件读出来、解析成 Python 对象，供上层使用。
#
# 小白导读（关键术语大白话）：
#   - Agent（智能体）：一个能自己思考+调用工具完成任务的 AI 程序，类比"员工"。
#   - LLM（大语言模型）：Agent 的"大脑"，负责理解任务和做决策。
#   - MCP（Model Context Protocol）：一套标准协议，让 AI 能调用外部工具，
#     类比"员工与公司内部系统之间的标准接口"。
#   - YAML frontmatter：Markdown 文件顶部用 --- 包裹的元数据块，
#     类比"简历最上方的基本信息栏"。
#   - Skills：可复用的能力模块，像"员工培训手册"，不同 Agent 可以共用。
#   - Rules：规则文件，像"员工手册里的规章制度"，约束 Agent 行为。
#   - 渐进式披露（Progressive Disclosure）：按需加载，先用轻量信息做判断，
#     需要时才加载详细内容，避免一次性把大量提示词塞给 LLM 导致"上下文爆炸"。
#
# 与其他文件的协作关系：
#   - 被 src/core/schemas.py 引用（本文件内嵌了 AgentMetadata 等数据类定义）。
#   - 被 src/agents/factory.py 调用，用于创建 Agent 实例时加载配置。
#   - 被 src/core/workflow.py 调用，工作流启动时加载 Agent 配置。
#   - 读取 config/agents/ 目录下的 AGENT.md 文件。
#   - 读取 config/mcp.yaml 文件获取 MCP 服务器配置。
#   - 读取 config/skills/ 目录下的 SKILL.md 文件。
# ============================================================================

"""Agent 配置加载器，支持渐进式披露（Progressive Disclosure）。

本模块实现智能加载器，遵循 Claude Agent Skills 规范：
- YAML frontmatter + Markdown 格式定义 Agent
- 三级加载：L1 元数据 → L2 指令 → L3 资源
- 支持 Skills、Rules 集成、每 Agent MCP 服务器配置

使用示例：
    loader = AgentConfigLoader()

    # L1：发现可用 Agent（轻量）
    agents = loader.discover_agents()

    # L2：触发 Agent 时加载完整系统提示词
    prompt = loader.load_system_prompt("process_agent")

    # L3：按需加载 Skills 和 MCP 配置
    skills = loader.load_skills("process_agent")
    mcp_config = loader.load_mcp_config("process_agent")
"""

from __future__ import annotations  # 支持 Python 3.9+ 的 | 类型语法，延迟类型注解求值

import os       # 用于读取环境变量（如 CONFIG_DIRECTORY）
import re       # 正则表达式，用于匹配 YAML frontmatter
from dataclasses import dataclass, field  # 数据类装饰器，自动生成 __init__ 等方法
from pathlib import Path  # 面向对象的路径操作，比 os.path 更现代
from typing import Any, Dict, List, Optional  # 类型提示

import yaml  # 解析 YAML 文件（frontmatter 和 mcp.yaml）

from ..logger import setup_logger  # 项目内部日志工具

# 创建本模块的日志实例，用于打印警告/错误信息
logger = setup_logger()


# --- 数据类定义 ---
# 用 @dataclass 自动生成 __init__、__repr__ 等方法，省去手写样板代码

@dataclass
class AgentMetadata:
    """从 YAML frontmatter 提取的 Agent 元数据（L1）。

    小白导读: 元数据就是"关于数据的数据"，这里存的是 Agent 的基本信息，
    类比"员工的工牌信息"——名字、岗位、版本号等，不含具体工作手册。

    Attributes:
        name: Agent 唯一标识符（小写+连字符）。
        description: Agent 用途简述。
        version: 语义版本号。
        model: 模型配置字典。
        skills: 要从共享 skills/ 文件夹加载的 Skill 名称列表。
        rules: rules 文件路径（字符串）或路径列表。
        mcp_servers: 要启用的 MCP 服务器名称列表。
        use_complete_prompt: 若 True，把 markdown 内容作为完整系统提示词使用。
    """
    name: str  # Agent 名称，如 "process_agent"
    description: str  # 一句话描述，如 "处理数据分析工作流"
    version: str = "1.0.0"  # 版本号，默认 1.0.0
    model: Dict[str, Any] = field(default_factory=dict)  # 模型配置，如 {"provider": "openai", "model": "gpt-4"}
    skills: List[str] = field(default_factory=list)  # 需要加载的 Skill 名称列表
    tools: List[str] = field(default_factory=list)  # 可用工具列表
    rules: Any = ""  # 可以是 str 或 List[str]，规则文件路径
    mcp_servers: List[str] = field(default_factory=list)  # MCP 服务器名称列表
    use_complete_prompt: bool = False  # 是否使用完整提示词

# 全局 MCP 总开关。
# True = 整个项目完全不加载任何 MCP 服务器（忽略所有服务器的配置与各 agent 的 mcp_servers 声明）。
# 设为 False 则恢复原有行为。
DISABLE_MCP_GLOBALLY: bool = True


@dataclass
class SkillConfig:
    """SKILL.md 文件的配置。

    小白导读: Skill 就是 Agent 的"技能培训手册"，不同 Agent 可以共用同一本手册。
    比如"代码搜索技能"可以被 code_agent 和 process_agent 同时使用。

    Attributes:
        name: Skill 唯一标识符。
        description: 用于发现和触发的简述。
        content: Skill 的完整 markdown 内容。
        path: Skill 文件的绝对路径。
    """
    name: str  # Skill 名称，如 "code_search"
    description: str  # 简述，如 "在代码库中搜索关键词"
    content: str  # SKILL.md 的完整内容
    path: Path  # 文件绝对路径，如 /project/config/skills/code_search/SKILL.md


@dataclass
class RuleConfig:
    """规则 markdown 文件的配置。

    小白导读: Rule 是"规章制度"，决定 Agent 在什么情况下必须做什么。
    比如"所有输出必须使用中文"就是一条规则。

    Attributes:
        trigger: 规则触发时机（always_on / on_demand / context_match）。
        priority: 规则应用优先级（值越大越先应用）。
        context_patterns: context_match 触发器的匹配模式。
        content: 规则的完整 markdown 内容。
        path: 规则文件的绝对路径。
    """
    trigger: str = "always_on"  # 触发时机：always_on 总是生效；on_demand 按需；context_match 上下文匹配
    priority: int = 100  # 优先级，值越大越先应用
    context_patterns: List[str] = field(default_factory=list)  # 上下文匹配模式
    content: str = ""  # 规则正文
    path: Optional[Path] = None  # 文件路径


class AgentConfigLoader:
    """支持渐进式披露的 Agent 智能加载器。

    三级加载策略：
    - L1：元数据（始终加载，轻量）—— 类比"先看工牌确认是谁"
    - L2：指令/系统提示词（Agent 触发时加载）—— 类比"再发工作手册"
    - L3：Skills、Rules、MCP 配置（按需加载）—— 类比"需要时才去查培训材料"

    这样设计是因为 LLM 的上下文窗口有限，一次塞太多内容会"记不住"。

    Attributes:
        config_root: Agent 配置的根目录。
    """

    # 匹配 YAML frontmatter 的正则
    # 小白导读: frontmatter 就是 Markdown 文件顶部用 --- 包裹的部分
    # 例如:
    # ---
    # name: code_agent
    # description: 写代码的助手
    # ---
    # 下面才是正文...
    FRONTMATTER_PATTERN = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n",  # 匹配 --- ... --- 之间的内容
        re.DOTALL  # 让 . 也能匹配换行符
    )

    def __init__(
        self,
        config_root: str | Path | None = None,
        mcp_config_path: str | Path | None = None
    ) -> None:
        """初始化加载器。

        Args:
            config_root: 包含 Agent 配置的根目录。
            mcp_config_path: MCP 服务器配置文件路径。
        """
        # 从环境变量加载基础配置目录，默认值为 "config"
        # 小白导读: 环境变量就是在操作系统里设置的全局参数
        # 例如在终端执行: export CONFIG_DIRECTORY=my_config
        config_dir = os.getenv('CONFIG_DIRECTORY', 'config')

        # 默认路径相对于 config_dir
        if config_root is None:
            config_root = os.path.join(config_dir, "agents")  # 默认 config/agents/
        if mcp_config_path is None:
            mcp_config_path = os.path.join(config_dir, "mcp.yaml")  # 默认 config/mcp.yaml

        self.config_root = Path(config_root)  # 转为 Path 对象，方便后续拼接路径
        self.mcp_config_path = Path(mcp_config_path)
        self._metadata_cache: Dict[str, AgentMetadata] = {}  # 缓存，避免重复读取文件
        self._mcp_config: Optional[Dict[str, Any]] = None  # MCP 配置缓存

    def discover_agents(self) -> List[str]:
        """发现所有可用 Agent（L1）。

        扫描 config_root 目录，查找包含 AGENT.md 的子目录。

        小白导读: 这个方法就像"点名"——去办公室看哪些员工今天在岗。
        每个 Agent 有自己的文件夹，里面必须有 AGENT.md 文件才算"在岗"。

        Returns:
            Agent 名称列表（目录名）。

        假数据示例:
            假设 config_root 下有:
                agents/
                    process_agent/AGENT.md
                    code_agent/AGENT.md
                    _hidden/AGENT.md  (下划线开头，会被忽略)
            返回: ["process_agent", "code_agent"]
        """
        agents = []
        if not self.config_root.exists():
            logger.warning(f"Agent config root does not exist: {self.config_root}")
            return agents

        for item in self.config_root.iterdir():
            if item.is_dir() and not item.name.startswith("_"):  # 跳过下划线开头的目录（私有/隐藏）
                agent_md = item / "AGENT.md"  # 拼接路径: agents/process_agent/AGENT.md
                if agent_md.exists():
                    agents.append(item.name)

        logger.info(f"Discovered {len(agents)} agents: {agents}")
        return agents

    def load_metadata(self, agent_name: str) -> AgentMetadata:
        """从 YAML frontmatter 加载 Agent 元数据（L1）。

        Args:
            agent_name: Agent 名称（目录名）。

        Returns:
            包含 frontmatter 数据的 AgentMetadata 数据类。

        Raises:
            FileNotFoundError: AGENT.md 不存在。
            ValueError: frontmatter 缺失或无效。

        假数据示例:
            输入: agent_name = "code_agent"
            AGENT.md 内容:
                ---
                name: code_agent
                description: 写代码的助手
                version: 2.0.0
                use_complete_prompt: true
                ---
                你是一个专业的代码助手...
            返回: AgentMetadata(name="code_agent", description="写代码的助手", version="2.0.0", ...)
        """
        # 缓存命中直接返回，避免重复磁盘读取
        if agent_name in self._metadata_cache:
            return self._metadata_cache[agent_name]

        agent_md_path = self.config_root / agent_name / "AGENT.md"  # 拼接完整路径
        if not agent_md_path.exists():
            raise FileNotFoundError(f"Agent config not found: {agent_md_path}")

        content = agent_md_path.read_text(encoding="utf-8")  # 读取文件全文
        frontmatter = self._extract_frontmatter(content)  # 提取 frontmatter 字典

        if not frontmatter:
            raise ValueError(f"No frontmatter found in {agent_md_path}")

        # 从 agent_config.yaml 读取扩展配置（skills/rules/mcp_servers）
        # 小白导读: 扩展配置单独放在 config.yaml 里，避免 frontmatter 太长
        ext_config = self._get_agent_extended_config(agent_name)

        metadata = AgentMetadata(
            name=frontmatter.get("name", agent_name),  # 优先用 frontmatter 的 name，没有则用目录名
            description=frontmatter.get("description", ""),
            version=frontmatter.get("version", "1.0.0"),
            model=frontmatter.get("model", {}),
            # skills/rules/mcp 从 agent_config.yaml 读取，而非 frontmatter
            skills=ext_config.get("skills", []),
            tools=ext_config.get("tools", []),
            rules=ext_config.get("rules", []),
            mcp_servers=ext_config.get("mcp_servers", []),
            use_complete_prompt=frontmatter.get("use_complete_prompt", False),
        )

        self._metadata_cache[agent_name] = metadata  # 写入缓存
        return metadata

    def load_system_prompt(self, agent_name: str) -> str:
        """从 AGENT.md 加载完整系统提示词（L2）。

        提取 frontmatter 之后的 markdown 内容作为系统提示词。

        小白导读: 系统提示词就是给 Agent 的"岗位说明书"，
        告诉它"你是谁、该怎么说话、做什么事"。

        Args:
            agent_name: Agent 名称。

        Returns:
            系统提示词字符串（markdown 内容）。

        Raises:
            FileNotFoundError: AGENT.md 不存在。

        假数据示例:
            输入: agent_name = "code_agent"
            AGENT.md 内容:
                ---
                name: code_agent
                ---
                你是一个专业的代码助手。
                请用中文回答。
            返回: "你是一个专业的代码助手。\n请用中文回答。"
        """
        agent_md_path = self.config_root / agent_name / "AGENT.md"
        if not agent_md_path.exists():
            raise FileNotFoundError(f"Agent config not found: {agent_md_path}")

        content = agent_md_path.read_text(encoding="utf-8")

        # 移除 frontmatter，取提示词内容
        match = self.FRONTMATTER_PATTERN.match(content)
        if match:
            prompt = content[match.end():].strip()  # 截取 frontmatter 之后的内容
        else:
            prompt = content.strip()

        # 加载并应用 Rules（规则内容追加到提示词末尾）
        rules_content = self._load_rules_content(agent_name)
        if rules_content:
            prompt = f"{prompt}\n\n{rules_content}"

        # 加载并应用 Skills（技能内容也追加到提示词末尾）
        skills_content = self._load_skills_content(agent_name)
        if skills_content:
            prompt = f"{prompt}\n\n{skills_content}"

        metadata = self.load_metadata(agent_name)
        if metadata.use_complete_prompt:
            return f"SYSTEM_PROMPT:{prompt}"  # 加前缀标记为完整提示词

        return prompt

    def load_skills(self, agent_name: str) -> List[SkillConfig]:
        """加载 Agent 特定的 Skills（L3）。

        小白导读: 这个方法去 config/skills/ 目录找对应的 SKILL.md 文件。
        比如 Agent 声明需要 "code_search" 技能，就去 skills/code_search/SKILL.md 读取。

        Args:
            agent_name: Agent 名称。

        Returns:
            SkillConfig 对象列表。

        假数据示例:
            输入: agent_name = "code_agent"
            metadata.skills = ["code_search", "git_ops"]
            config/skills/code_search/SKILL.md 存在
            config/skills/git_ops/SKILL.md 不存在
            返回: [SkillConfig(name="code_search", ...)]
            同时打印警告: "Skill not found: git_ops"
        """
        metadata = self.load_metadata(agent_name)
        skills = []
        # skills 文件夹位于 config/skills/（agents/ 的兄弟目录）
        # 小白导读: parent 就是上一级目录，agents/ 的父目录就是 config/
        skills_dir = self.config_root.parent / "skills"

        for skill_name in metadata.skills:
            # Skill 通过名称引用，存储在共享 skills/ 文件夹中
            skill_path = skills_dir / skill_name / "SKILL.md"
            if skill_path.exists():
                skill = self._parse_skill_file(skill_path)
                if skill:
                    skills.append(skill)
            else:
                logger.warning(f"Skill not found: {skill_name}")

        return skills

    def get_skill_content(self, skill_name: str) -> Optional[str]:
        """获取 Skill 文件的完整内容（L2）。

        Args:
            skill_name: Skill 名称。

        Returns:
            SKILL.md 文件内容，或 None（未找到时）。

        假数据示例:
            输入: skill_name = "code_search"
            返回: "# Code Search Skill\n\nThis skill enables..." 或 None
        """
        skills_dir = self.config_root.parent / "skills"
        skill_path = skills_dir / skill_name / "SKILL.md"

        if not skill_path.exists():
            logger.warning(f"Skill file not found: {skill_path}")
            return None

        return skill_path.read_text(encoding="utf-8")

    def load_rules(self, agent_name: str) -> List[RuleConfig]:
        """加载 Agent 适用的 Rules（L3）。

        小白导读: 规则文件可以来自两个地方：
        1. Agent 自己的目录（rules/my_rule.md）
        2. 共享目录（rules/_shared_rule.md，以 _ 开头表示共享）

        Args:
            agent_name: Agent 名称。

        Returns:
            RuleConfig 列表，按优先级降序排列。

        假数据示例:
            输入: agent_name = "code_agent"
            metadata.rules = ["coding_rules.md", "_shared_rules.md"]
            返回: [RuleConfig(priority=200, ...), RuleConfig(priority=100, ...)]  # 高优先级在前
        """
        metadata = self.load_metadata(agent_name)
        rules = []

        rule_path = metadata.rules
        if not rule_path:
            return rules

        # 兼容字符串和列表（rules 可以写成一个路径或多个路径）
        if isinstance(rule_path, str):
            rule_paths = [rule_path]
        else:
            rule_paths = rule_path

        for rp in rule_paths:
            # 以 "_" 开头的路径相对于 config_root（共享）
            if rp.startswith("_"):
                full_path = (self.config_root / rp).resolve()
            else:
                agent_dir = self.config_root / agent_name
                full_path = (agent_dir / rp).resolve()

            if full_path.exists():
                rule = self._parse_rule_file(full_path)
                if rule:
                    rules.append(rule)
            else:
                logger.warning(f"Rule file not found: {full_path}")

        # 按优先级降序排列（数值大的先应用）
        rules.sort(key=lambda r: r.priority, reverse=True)
        return rules

    def load_mcp_config(self, agent_name: str) -> Dict[str, Any]:
        """加载 Agent 的 MCP 服务器配置（L3）。

        合并默认 MCP 服务器和 Agent 特定的覆盖配置。

        小白导读: MCP 配置存储在 config/mcp.yaml 里，定义了 Agent 可以调用哪些外部工具。
        比如一个 Agent 可以调用"数据库服务器"和"搜索引擎服务器"。

        Args:
            agent_name: Agent 名称。

        Returns:
            包含 'servers' 键的字典，含已启用的服务器配置。

        假数据示例:
            输入: agent_name = "code_agent"
            mcp.yaml 内容:
                servers:
                    db: {command: "python", args: ["db_server.py"]}
                    search: {command: "node", args: ["search_server.js"]}
                defaults: [db]
            metadata.mcp_servers = ["search"]
            返回: {
                "servers": {
                    "db": {command: "python", args: ["db_server.py"]},
                    "search": {command: "node", args: ["search_server.js"]}
                }
            }
        """
        # 全局 MCP 总开关：关闭时直接返回空配置，不读取 mcp.yaml。
        if DISABLE_MCP_GLOBALLY:
            return {"servers": {}, "defaults": []}

        # 首次调用时加载 mcp.yaml 并缓存
        if self._mcp_config is None:
            self._mcp_config = self._load_mcp_config_file()

        metadata = self.load_metadata(agent_name)
        all_servers = self._mcp_config.get("servers", {})  # 所有可用服务器
        defaults = self._mcp_config.get("defaults", [])  # 默认启用的服务器

        # 合并默认服务器和 Agent 特定服务器（取并集）
        enabled_servers = set(defaults) | set(metadata.mcp_servers)

        result = {
            "servers": {
                name: config
                for name, config in all_servers.items()
                if name in enabled_servers  # 只保留已启用的
            }
        }

        return result

    def get_model_config(self, agent_name: str) -> Dict[str, Any]:
        """从 Agent 元数据获取模型配置。

        小白导读: 模型配置告诉程序"该用哪个 AI 大脑"，比如用 GPT-4 还是 Claude。

        Args:
            agent_name: Agent 名称。

        Returns:
            包含 provider 和 model_config 的字典。

        假数据示例:
            输入: agent_name = "code_agent"
            返回: {"provider": "openai", "model": "gpt-4", "temperature": 0.7}
        """
        metadata = self.load_metadata(agent_name)
        return metadata.model

    def _extract_frontmatter(self, content: str) -> Optional[Dict[str, Any]]:
        """从 markdown 内容中提取 YAML frontmatter。

        这是一个私有方法（下划线开头），供内部使用。

        Args:
            content: 完整的 markdown 文件内容。

        Returns:
            解析后的 YAML 字典，或 None（无 frontmatter 时）。

        假数据示例:
            输入: "---\nname: test\n---\n正文内容"
            返回: {"name": "test"}
        """
        match = self.FRONTMATTER_PATTERN.match(content)
        if not match:
            return None

        try:
            return yaml.safe_load(match.group(1))  # safe_load 安全解析 YAML，避免执行恶意代码
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse frontmatter: {e}")
            return None

    def _parse_skill_file(self, path: Path) -> Optional[SkillConfig]:
        """解析 SKILL.md 文件为 SkillConfig。

        Args:
            path: Skill 文件路径。

        Returns:
            SkillConfig 或 None（解析失败时）。

        假数据示例:
            输入: path = Path("/project/config/skills/code_search/SKILL.md")
            返回: SkillConfig(name="code_search", description="搜索代码", content="...", path=...)
        """
        content = path.read_text(encoding="utf-8")
        frontmatter = self._extract_frontmatter(content)

        if not frontmatter:
            logger.warning(f"No frontmatter in skill file: {path}")
            return None

        return SkillConfig(
            name=frontmatter.get("name", path.stem),  # path.stem 是文件名去掉扩展名
            description=frontmatter.get("description", ""),
            content=content,
            path=path,
        )

    def _parse_rule_file(self, path: Path) -> Optional[RuleConfig]:
        """解析规则 markdown 文件为 RuleConfig。

        Args:
            path: 规则文件路径。

        Returns:
            RuleConfig 或 None（解析失败时）。

        假数据示例:
            输入: path = Path("/project/config/agents/code_agent/rules/coding.md")
            返回: RuleConfig(trigger="always_on", priority=200, content="规则正文...", path=...)
        """
        content = path.read_text(encoding="utf-8")
        frontmatter = self._extract_frontmatter(content)

        if not frontmatter:
            # 无 frontmatter 的规则默认为 always_on（始终生效）
            return RuleConfig(
                trigger="always_on",
                priority=100,
                content=content,
                path=path,
            )

        # 移除 frontmatter 获取规则内容
        match = self.FRONTMATTER_PATTERN.match(content)
        rule_content = content[match.end():].strip() if match else content

        return RuleConfig(
            trigger=frontmatter.get("trigger", "always_on"),
            priority=frontmatter.get("priority", 100),
            context_patterns=frontmatter.get("context_patterns", []),
            content=rule_content,
            path=path,
        )

    def _load_rules_content(self, agent_name: str) -> str:
        """加载并合并 Agent 的规则内容。

        小白导读: 只加载 trigger="always_on" 的规则，拼成一个字符串返回。

        Args:
            agent_name: Agent 名称。

        Returns:
            合并后的规则内容字符串。

        假数据示例:
            输入: agent_name = "code_agent"
            假设加载到 2 条 always_on 规则
            返回: "## Applied Rules\n规则1内容...\n\n规则2内容..."
        """
        rules = self.load_rules(agent_name)
        active_rules = [r for r in rules if r.trigger == "always_on"]  # 只取始终生效的规则

        if not active_rules:
            return ""

        sections = ["## Applied Rules"]  # 标题
        for rule in active_rules:
            sections.append(rule.content)

        return "\n\n".join(sections)

    def _load_skills_content(self, agent_name: str) -> str:
        """加载并合并 Agent 的 Skills 内容。

        小白导读: 只加载每个 Skill 的名称和描述（不加载完整内容），
        避免系统提示词过长。完整内容在 Agent 需要时才单独获取。

        Args:
            agent_name: Agent 名称。

        Returns:
            合并后的 Skills 内容字符串。

        假数据示例:
            输入: agent_name = "code_agent"
            假设加载到 2 个 Skill
            返回: "## Available Skills\n\n### code_search\n在代码中搜索关键词\n\n### git_ops\n执行 Git 操作"
        """
        skills = self.load_skills(agent_name)

        if not skills:
            return ""

        sections = ["## Available Skills"]
        for skill in skills:
            sections.append(f"### {skill.name}\n{skill.description}")  # 只取名称+描述

        return "\n\n".join(sections)

    def _load_mcp_config_file(self) -> Dict[str, Any]:
        """从 YAML 文件加载 MCP 配置。

        小白导读: 这个方法读取 config/mcp.yaml 并解析成 Python 字典。
        支持环境变量展开，比如 password: ${DB_PASSWORD} 会自动替换。

        Returns:
            MCP 配置字典。

        假数据示例:
            假设 mcp.yaml 内容:
                servers:
                    db: {command: "python", args: ["db.py"]}
                defaults: [db]
            返回: {"servers": {"db": {"command": "python", "args": ["db.py"]}}, "defaults": ["db"]}
        """
        if not self.mcp_config_path.exists():
            logger.warning(f"MCP config not found: {self.mcp_config_path}")
            return {"servers": {}, "defaults": []}

        try:
            content = self.mcp_config_path.read_text(encoding="utf-8")
            config = yaml.safe_load(content)

            # 递归展开配置中的环境变量（如 ${DB_PASSWORD}）
            return self._expand_env_vars(config)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse MCP config: {e}")
            return {"servers": {}, "defaults": []}

    def _expand_env_vars(self, obj: Any) -> Any:
        """递归展开配置中的环境变量。

        支持 ${VAR_NAME} 语法。

        小白导读: 这个方法让配置文件里可以引用系统环境变量。
        比如 mcp.yaml 里写 password: ${DB_PASSWORD}，
        程序运行时就会自动替换成系统里设置的 DB_PASSWORD 值。

        Args:
            obj: 配置对象（dict、list 或 str）。

        Returns:
            展开环境变量后的对象。

        假数据示例:
            假设环境变量 DB_PASSWORD = "secret123"
            输入: {"password": "${DB_PASSWORD}", "timeout": 30}
            返回: {"password": "secret123", "timeout": 30}
        """
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}  # 递归处理字典的值
        elif isinstance(obj, list):
            return [self._expand_env_vars(item) for item in obj]  # 递归处理列表的每个元素
        elif isinstance(obj, str):
            # 匹配 ${VAR_NAME} 模式
            pattern = re.compile(r"\$\{([^}]+)\}")
            def replace(match: re.Match) -> str:
                var_name = match.group(1)  # 提取变量名
                return os.environ.get(var_name, match.group(0))  # 找不到则保留原样
            return pattern.sub(replace, obj)
        return obj  # 其他类型（int/float/bool）直接返回

    def _load_per_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """从 config.yaml 加载每 Agent 配置。

        小白导读: 每个 Agent 目录下可以有自己的 config.yaml，
        声明该 Agent 需要哪些 Skills、Rules、MCP 服务器。

        Args:
            agent_name: Agent 名称。

        Returns:
            Agent 配置字典。

        假数据示例:
            输入: agent_name = "code_agent"
            config/agents/code_agent/config.yaml 内容:
                skills: [code_search]
                tools: [bash, file_reader]
                rules: [coding_rules.md]
                mcp_servers: [db]
            返回: {"skills": ["code_search"], "tools": ["bash", "file_reader"],
                   "rules": ["coding_rules.md"], "mcp_servers": ["db"]}
        """
        config_path = self.config_root / agent_name / "config.yaml"
        if not config_path.exists():
            logger.debug(f"No config.yaml for agent: {agent_name}")
            return {"skills": [], "tools": [], "rules": [], "mcp_servers": []}

        try:
            content = config_path.read_text(encoding="utf-8")
            config = yaml.safe_load(content) or {}  # safe_load 可能返回 None（空文件）
            return {
                "skills": config.get("skills", []),
                "tools": config.get("tools", []),
                "rules": config.get("rules", []),
                "mcp_servers": config.get("mcp_servers", []),
            }
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse config.yaml for {agent_name}: {e}")
            return {"skills": [], "tools": [], "rules": [], "mcp_servers": []}

    def _get_agent_extended_config(self, agent_name: str) -> Dict[str, Any]:
        """获取 Agent 的扩展配置（skills/rules/mcp）。

        从 Agent 自己的 config.yaml 文件读取。

        小白导读: 这个方法是 _load_per_agent_config 的"包装器"，
        以后如果需要在读取配置时加逻辑（如合并全局配置），只改这里就行。

        Args:
            agent_name: Agent 名称。

        Returns:
            包含 skills、rules、mcp_servers 的字典。
        """
        return self._load_per_agent_config(agent_name)


# 全局单例
# 小白导读: 单例模式——整个程序只创建一个 loader 实例，
# 避免重复创建和浪费内存。类比"全公司只有一个 HR 部门"。
_default_loader: Optional[AgentConfigLoader] = None


def get_agent_config_loader() -> AgentConfigLoader:
    """获取默认的 AgentConfigLoader 单例。

    小白导读: 这是"获取单例"的函数。第一次调用时创建实例，
    之后每次调用都返回同一个实例。

    Returns:
        AgentConfigLoader 实例。

    假数据示例:
        第一次调用: 创建 AgentConfigLoader() 并返回
        第二次调用: 直接返回已创建的实例（不重新创建）
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = AgentConfigLoader()  # 首次调用时创建
    return _default_loader
