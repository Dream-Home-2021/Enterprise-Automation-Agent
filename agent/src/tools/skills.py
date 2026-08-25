from typing import Optional, Type


from langchain.tools import BaseTool


from pydantic import BaseModel, Field


from ..core.agent_config_loader import get_agent_config_loader


from ..logger import setup_logger

# 创建一个模块级别的 logger 实例

logger = setup_logger()


class LookupSkillInput(BaseModel):
    """
    """

    skill_name: str = Field(description="Name of the skill to lookup (from Available Skills list)")


class LookupSkill(BaseTool):
    """
    """

    name: str = "lookup_skill"


    # 类比 "工具的包装盒上的说明"
    description: str = (
        "Retrieve detailed instructions and content for a specific skill. "
        "Use this when you need procedural knowledge or workflows defined in a skill."
    )


    # 类比 "报名表的格式要求"
    args_schema: Type[BaseModel] = LookupSkillInput

    def _run(self, skill_name: str) -> str:
        """
        """
        # 获取全局配置加载器实例（单例模式）

        loader = get_agent_config_loader()


        content = loader.get_skill_content(skill_name)

        if content:

            # 日志用于排查问题，不会返回给用户看——类比 "老师的批改记录"
            logger.info(f"Agent looked up skill: {skill_name}")

            return content
        else:
            # 构建错误提示消息

            # 类比 "填空题"，花括号处填入实际值
            msg = f"Error: Skill '{skill_name}' not found. Please check the 'Available Skills' list."


            # 与 info 的区别是 warning 表示"出现了需要注意但不是致命的问题"
            logger.warning(f"Skill lookup failed: {skill_name}")

            return msg

    async def _arun(self, skill_name: str) -> str:
        """
        """

        # 这是一种常见模式：当同步与异步逻辑完全相同时，在异步方法中直接转发
        # 类比 "速溶咖啡和现磨咖啡味道一样，就直接用速溶的"
        return self._run(skill_name)
