"""Agent Progressive Disclosure

    loader = AgentConfigLoader()

    agents = loader.discover_agents()

    prompt = loader.load_system_prompt("process_agent")

    skills = loader.load_skills("process_agent")
    mcp_config = loader.load_mcp_config("process_agent")
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..logger import setup_logger

logger = setup_logger()


# --- 数据类定义 ---
# 用 @dataclass 自动生成 __init__、__repr__ 等方法，省去手写样板代码

@dataclass
class AgentMetadata:
    """ YAML frontmatter  Agent L1

    Attributes:
    """
    name: str
    description: str
    version: str = "1.0.0"
    model: Dict[str, Any] = field(default_factory=dict)
    skills: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    rules: Any = ""
    mcp_servers: List[str] = field(default_factory=list)
    use_complete_prompt: bool = False

# 全局 MCP 总开关。
# True = 整个项目完全不加载任何 MCP 服务器（忽略所有服务器的配置与各 agent 的 mcp_servers 声明）。
# 设为 False 则恢复原有行为。
DISABLE_MCP_GLOBALLY: bool = True


@dataclass
class SkillConfig:
    """SKILL.md 

    Attributes:
    """
    name: str
    description: str
    content: str
    path: Path


@dataclass
class RuleConfig:
    """ markdown 

    Attributes:
    """
    trigger: str = "always_on"
    priority: int = 100
    context_patterns: List[str] = field(default_factory=list)
    content: str = ""
    path: Optional[Path] = None


class AgentConfigLoader:
    """ Agent 

    Attributes:
    """

    # 匹配 YAML frontmatter 的正则

    FRONTMATTER_PATTERN = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n",
        re.DOTALL
    )

    def __init__(
        self,
        config_root: str | Path | None = None,
        mcp_config_path: str | Path | None = None
    ) -> None:
        """

        Args:
            config_root: 包含 Agent 配置的根目录。
            mcp_config_path: MCP 服务器配置文件路径。
        """

        # 例如在终端执行: export CONFIG_DIRECTORY=my_config
        config_dir = os.getenv('CONFIG_DIRECTORY', 'config')

        if config_root is None:
            config_root = os.path.join(config_dir, "agents")
        if mcp_config_path is None:
            mcp_config_path = os.path.join(config_dir, "mcp.yaml")

        self.config_root = Path(config_root)
        self.mcp_config_path = Path(mcp_config_path)
        self._metadata_cache: Dict[str, AgentMetadata] = {}
        self._mcp_config: Optional[Dict[str, Any]] = None

    def discover_agents(self) -> List[str]:
        """ AgentL1

        Returns:
            Agent 名称列表（目录名）。
        """
        agents = []
        if not self.config_root.exists():
            logger.warning(f"Agent config root does not exist: {self.config_root}")
            return agents

        for item in self.config_root.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                agent_md = item / "AGENT.md"
                if agent_md.exists():
                    agents.append(item.name)

        logger.info(f"Discovered {len(agents)} agents: {agents}")
        return agents

    def load_metadata(self, agent_name: str) -> AgentMetadata:
        """ YAML frontmatter  Agent L1

        Args:
            agent_name: Agent 名称（目录名）。

        Returns:
            包含 frontmatter 数据的 AgentMetadata 数据类。

        Raises:
            FileNotFoundError: AGENT.md 不存在。
            ValueError: frontmatter 缺失或无效。
        """
        if agent_name in self._metadata_cache:
            return self._metadata_cache[agent_name]

        agent_md_path = self.config_root / agent_name / "AGENT.md"
        if not agent_md_path.exists():
            raise FileNotFoundError(f"Agent config not found: {agent_md_path}")

        content = agent_md_path.read_text(encoding="utf-8")
        frontmatter = self._extract_frontmatter(content)

        if not frontmatter:
            raise ValueError(f"No frontmatter found in {agent_md_path}")


        ext_config = self._get_agent_extended_config(agent_name)

        metadata = AgentMetadata(
            name=frontmatter.get("name", agent_name),
            description=frontmatter.get("description", ""),
            version=frontmatter.get("version", "1.0.0"),
            model=frontmatter.get("model", {}),
            skills=ext_config.get("skills", []),
            tools=ext_config.get("tools", []),
            rules=ext_config.get("rules", []),
            mcp_servers=ext_config.get("mcp_servers", []),
            use_complete_prompt=frontmatter.get("use_complete_prompt", False),
        )

        self._metadata_cache[agent_name] = metadata
        return metadata

    def load_system_prompt(self, agent_name: str) -> str:
        """ AGENT.md L2

        Args:
            agent_name: Agent 名称。

        Returns:
            系统提示词字符串（markdown 内容）。

        Raises:
            FileNotFoundError: AGENT.md 不存在。
        """
        agent_md_path = self.config_root / agent_name / "AGENT.md"
        if not agent_md_path.exists():
            raise FileNotFoundError(f"Agent config not found: {agent_md_path}")

        content = agent_md_path.read_text(encoding="utf-8")

        match = self.FRONTMATTER_PATTERN.match(content)
        if match:
            prompt = content[match.end():].strip()
        else:
            prompt = content.strip()

        rules_content = self._load_rules_content(agent_name)
        if rules_content:
            prompt = f"{prompt}\n\n{rules_content}"

        skills_content = self._load_skills_content(agent_name)
        if skills_content:
            prompt = f"{prompt}\n\n{skills_content}"

        metadata = self.load_metadata(agent_name)
        if metadata.use_complete_prompt:
            return f"SYSTEM_PROMPT:{prompt}"

        return prompt

    def load_skills(self, agent_name: str) -> List[SkillConfig]:
        """ Agent  SkillsL3

        Args:
            agent_name: Agent 名称。

        Returns:
            SkillConfig 对象列表。
        """
        metadata = self.load_metadata(agent_name)
        skills = []

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
        """ Skill L2

        Args:
            skill_name: Skill 名称。

        Returns:
            SKILL.md 文件内容，或 None（未找到时）。
        """
        skills_dir = self.config_root.parent / "skills"
        skill_path = skills_dir / skill_name / "SKILL.md"

        if not skill_path.exists():
            logger.warning(f"Skill file not found: {skill_path}")
            return None

        return skill_path.read_text(encoding="utf-8")

    def load_rules(self, agent_name: str) -> List[RuleConfig]:
        """ Agent  RulesL3

        Args:
            agent_name: Agent 名称。

        Returns:
            RuleConfig 列表，按优先级降序排列。
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
        """ Agent  MCP L3

        Args:
            agent_name: Agent 名称。

        Returns:
            包含 'servers' 键的字典，含已启用的服务器配置。
        """
        if DISABLE_MCP_GLOBALLY:
            return {"servers": {}, "defaults": []}

        # 首次调用时加载 mcp.yaml 并缓存
        if self._mcp_config is None:
            self._mcp_config = self._load_mcp_config_file()

        metadata = self.load_metadata(agent_name)
        all_servers = self._mcp_config.get("servers", {})
        defaults = self._mcp_config.get("defaults", [])

        enabled_servers = set(defaults) | set(metadata.mcp_servers)

        result = {
            "servers": {
                name: config
                for name, config in all_servers.items()
                if name in enabled_servers
            }
        }

        return result

    def get_model_config(self, agent_name: str) -> Dict[str, Any]:
        """ Agent 

        Args:
            agent_name: Agent 名称。

        Returns:
            包含 provider 和 model_config 的字典。
        """
        metadata = self.load_metadata(agent_name)
        return metadata.model

    def _extract_frontmatter(self, content: str) -> Optional[Dict[str, Any]]:
        """ markdown  YAML frontmatter

        Args:
            content: 完整的 markdown 文件内容。

        Returns:
            解析后的 YAML 字典，或 None（无 frontmatter 时）。
        """
        match = self.FRONTMATTER_PATTERN.match(content)
        if not match:
            return None

        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse frontmatter: {e}")
            return None

    def _parse_skill_file(self, path: Path) -> Optional[SkillConfig]:
        """ SKILL.md  SkillConfig

        Args:
            path: Skill 文件路径。

        Returns:
            SkillConfig 或 None（解析失败时）。
        """
        content = path.read_text(encoding="utf-8")
        frontmatter = self._extract_frontmatter(content)

        if not frontmatter:
            logger.warning(f"No frontmatter in skill file: {path}")
            return None

        return SkillConfig(
            name=frontmatter.get("name", path.stem),
            description=frontmatter.get("description", ""),
            content=content,
            path=path,
        )

    def _parse_rule_file(self, path: Path) -> Optional[RuleConfig]:
        """ markdown  RuleConfig

        Args:
            path: 规则文件路径。

        Returns:
            RuleConfig 或 None（解析失败时）。
        """
        content = path.read_text(encoding="utf-8")
        frontmatter = self._extract_frontmatter(content)

        if not frontmatter:
            return RuleConfig(
                trigger="always_on",
                priority=100,
                content=content,
                path=path,
            )

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
        """ Agent 

        Args:
            agent_name: Agent 名称。

        Returns:
            合并后的规则内容字符串。
        """
        rules = self.load_rules(agent_name)
        active_rules = [r for r in rules if r.trigger == "always_on"]

        if not active_rules:
            return ""

        sections = ["## Applied Rules"]
        for rule in active_rules:
            sections.append(rule.content)

        return "\n\n".join(sections)

    def _load_skills_content(self, agent_name: str) -> str:
        """ Agent  Skills 

        Args:
            agent_name: Agent 名称。

        Returns:
            合并后的 Skills 内容字符串。
        """
        skills = self.load_skills(agent_name)

        if not skills:
            return ""

        sections = ["## Available Skills"]
        for skill in skills:
            sections.append(f"### {skill.name}\n{skill.description}")

        return "\n\n".join(sections)

    def _load_mcp_config_file(self) -> Dict[str, Any]:
        """ YAML  MCP 

        Returns:
            MCP 配置字典。
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
        """

        Args:
            obj: 配置对象（dict、list 或 str）。

        Returns:
            展开环境变量后的对象。
        """
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            pattern = re.compile(r"\$\{([^}]+)\}")
            def replace(match: re.Match) -> str:
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))
            return pattern.sub(replace, obj)
        return obj

    def _load_per_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """ config.yaml  Agent 

        Args:
            agent_name: Agent 名称。

        Returns:
            Agent 配置字典。
        """
        config_path = self.config_root / agent_name / "config.yaml"
        if not config_path.exists():
            logger.debug(f"No config.yaml for agent: {agent_name}")
            return {"skills": [], "tools": [], "rules": [], "mcp_servers": []}

        try:
            content = config_path.read_text(encoding="utf-8")
            config = yaml.safe_load(content) or {}
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
        """ Agent skills/rules/mcp

        Args:
            agent_name: Agent 名称。

        Returns:
            包含 skills、rules、mcp_servers 的字典。
        """
        return self._load_per_agent_config(agent_name)



# 避免重复创建和浪费内存。类比"全公司只有一个 HR 部门"。
_default_loader: Optional[AgentConfigLoader] = None


def get_agent_config_loader() -> AgentConfigLoader:
    """ AgentConfigLoader 

    Returns:
        AgentConfigLoader 实例。
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = AgentConfigLoader()
    return _default_loader
