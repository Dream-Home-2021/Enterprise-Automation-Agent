# ================================================================
# 文件角色: src/tools/skills.py
# 本文件定义了 Agent 可以使用的"技能查找工具"。
# 当 Agent 需要执行某项操作时，可以通过这个工具查询该技能的详细说明。
#
# 小白导读（给初学者的阅读指南）：
# - 工具(Tool): Agent 的能力扩展单元，类比"手"——Agent 用手去操作外部世界。
# - Agent: 一个具备自主决策能力的 AI 助手，类比"学生"——能根据目标选择行动。
# - 技能(Skill): 一份预定义的操作指南，类比"实验手册"——详细描述完成某任务的步骤。
# - LLM (Large Language Model): 大语言模型，类比"大脑"——负责思考和生成文本。
# - MCP (Model Context Protocol): 模型上下文协议，类比"USB接口"——统一了 LLM 与外部工具的通信标准。
# - BaseTool: LangChain 中所有工具的基类，提供 `_run`(同步) 和 `_arun`(异步) 接口。
# - Pydantic BaseModel: 用于定义数据结构的库，自带类型校验，类比"表格模板"。
# - Field: Pydantic 中用于给字段添加描述的装饰器，帮助 LLM 理解字段含义。
#
# 与其他文件的协作关系：
# - ..core.agent_config_loader: 提供配置加载能力（从 YAML/JSON 中读取技能定义）
# - ..logger: 提供结构化日志输出能力
# - langchain.tools.BaseTool: 继承基类以符合 LangChain 工具协议
# - 本文件定义的 LookupSkill 会被 src/tools/factory.py 注册到工具列表中
# ================================================================

# 小白导读: Optional 是类型注解，表示"可以为空"，类比"可能是 X 也可能是 None"
from typing import Optional, Type

# 小白导读: BaseTool 是 LangChain 框架中所有工具的基类
# 类比 "工具的标准模板"——所有工具都要继承它
from langchain.tools import BaseTool

# 小白导读: Pydantic 是用于数据校验的库，BaseModel 是所有数据模型的"模板"
from pydantic import BaseModel, Field

# 导入项目内部的配置加载器——负责从配置文件中读取技能定义
# 小白导读: get_agent_config_loader 是一个"工厂函数"，返回一个全局唯一的配置加载器实例
from ..core.agent_config_loader import get_agent_config_loader

# 导入项目内部的日志模块——用于输出运行时信息
# 小白导读: setup_logger() 返回一个配置好的 logger 实例，类比"准备好一个笔记本"来记录日志
from ..logger import setup_logger

# 创建一个模块级别的 logger 实例
# 小白导读: 模块级变量在整个文件中共享，所有函数都能使用这个 logger
logger = setup_logger()


class LookupSkillInput(BaseModel):
    """
    LookupSkill 工具的输入参数模型。
    定义了调用工具时必须传入哪些字段、每个字段的类型和含义。

    假数据示例:
        Input:  {"skill_name": "web_search"}
        Input:  {"skill_name": ""}
    """
    # skill_name 是查找技能时使用的名称
    # 小白导读: Field(description=...) 中的 description 会被发给 LLM，帮助 LLM 理解这个字段该填什么
    # 类比 "考试题目上的说明文字"
    skill_name: str = Field(description="Name of the skill to lookup (from Available Skills list)")


class LookupSkill(BaseTool):
    """
    Agent 使用的技能查找工具。
    当 Agent 需要执行某项技能但缺少具体操作步骤时，
    可以调用此工具获取该技能的完整指令内容。

    工作原理：
        Agent 提供技能名称 → 本工具从配置文件中读取内容 → 返回给 Agent 执行

    假数据示例:
        输入:  skill_name = "code_review"
        输出: "## Code Review 技能指南\n1. 阅读 PR 描述\n2. 查看代码变更..."

        输入:  skill_name = "nonexistent_skill"
        输出: "Error: Skill 'nonexistent_skill' not found. Please check the 'Available Skills' list."
    """
    # 小白导读: name 是工具的"身份证号"，Agent 通过这个名字来调用工具
    # 必须全局唯一，通常在 src/tools/factory.py 中通过这个名字查找工具
    name: str = "lookup_skill"

    # description 告诉 LLM 这个工具是干什么的、什么时候该用它
    # 小白导读: 这里写的内容会作为"工具说明书"发给 LLM，LLM 据此决定是否调用
    # 类比 "工具的包装盒上的说明"
    description: str = (
        "Retrieve detailed instructions and content for a specific skill. "
        "Use this when you need procedural knowledge or workflows defined in a skill."
    )

    # 小白导读: args_schema 声明输入参数的类型约束，LangChain 会用它自动校验输入
    # 类比 "报名表的格式要求"
    args_schema: Type[BaseModel] = LookupSkillInput

    def _run(self, skill_name: str) -> str:
        """
        【核心逻辑】同步查找技能内容的主流程。

        流程拆解：
            1. 获取全局唯一的配置加载器实例
            2. 调用 loader.get_skill_content() 根据技能名称查找对应内容
            3. 如果找到则返回内容；没找到则返回错误提示消息

        参数:
            skill_name: Agent 要查找的技能名称，例如 "code_review"

        返回:
            技能内容字符串，或错误提示字符串

        假数据示例:
            调用: _run("code_review")
            返回: "## Code Review 技能指南\n请仔细阅读..."

            调用: _run("unknown_skill")
            返回: "Error: Skill 'unknown_skill' not found..."
        """
        # 获取全局配置加载器实例（单例模式）
        # 小白导读: get_agent_config_loader() 返回的对象在整个程序中只有一份
        # 类比 "全校只有一本选课手册"
        loader = get_agent_config_loader()

        # 通过 loader 查找 skill_name 对应的具体内容
        # 小白导读: 这里实际执行的是对配置文件的 I/O 操作（读取文件）
        # 配置文件通常在项目根目录的 configs/ 或类似路径下
        # 如果文件不存在或 key 没找到，返回 None 或 ""
        content = loader.get_skill_content(skill_name)

        # 判断查找是否成功
        if content:
            # 小白导读: logger.info() 输出"信息级别"的日志
            # 日志用于排查问题，不会返回给用户看——类比 "老师的批改记录"
            logger.info(f"Agent looked up skill: {skill_name}")

            # 返回找到的技能内容，Agent 拿到后会按照这个内容执行
            return content
        else:
            # 构建错误提示消息
            # 小白导读: f-string 是 Python 中字符串格式化的方式，花括号 {} 内会被替换为变量值
            # 类比 "填空题"，花括号处填入实际值
            msg = f"Error: Skill '{skill_name}' not found. Please check the 'Available Skills' list."

            # 小白导读: logger.warning() 输出"警告级别"的日志
            # 与 info 的区别是 warning 表示"出现了需要注意但不是致命的问题"
            logger.warning(f"Skill lookup failed: {skill_name}")

            # 返回错误消息给 Agent，Agent 看到后会停止并报错给用户
            return msg

    async def _arun(self, skill_name: str) -> str:
        """
        【Python 的魔法方法】异步版本的主流程。
        LangChain 框架在运行时如果有异步调用机制，会优先调用这个异步版本。

        小白导读:
            - async: 表示这是一个"可以被暂停和恢复"的函数
            - 类比 "你去餐厅点餐（发出请求）后可以去旁边玩，叫号了再回来取"
            - 同步版本 _run() 则是"站在窗口等，拿到餐才离开"

        当前实现: 直接转发给 _run()，因为 loader 的查找操作本身就是同步的，
        没有真正的 I/O 异步等待，所以没有必要写额外的 async 逻辑。
        """
        # 小白导读: 直接调用同步版本的实现
        # 这是一种常见模式：当同步与异步逻辑完全相同时，在异步方法中直接转发
        # 类比 "速溶咖啡和现磨咖啡味道一样，就直接用速溶的"
        return self._run(skill_name)
