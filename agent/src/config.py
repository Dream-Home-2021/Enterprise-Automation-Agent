# ============================================================================
# 文件角色：项目全局配置中心（环境变量 + Agent 模型配置）
# 小白导读：
#   - API Key：访问第三方服务（如 OpenAI、LangChain）的"通行证"，类比银行卡密码
#   - .env 文件：存放敏感信息的本地配置文件，不提交到代码仓库
#   - YAML：一种用缩进表示层级的配置文件格式，类比"结构化的文本说明书"
#   - Conda：Python 的虚拟环境管理器，类比"独立隔离的工作台"
#   - ChromeDriver：控制 Chrome 浏览器的驱动程序，让代码能自动操作网页
# 协作关系：
#   - 被 src/agents/* 读取，决定每个 Agent 使用哪个 LLM 模型
#   - 被 src/core/* 读取，获取工作目录、配置目录等路径
# ============================================================================
import os  # 操作系统接口，用于读取环境变量、拼接路径
from dotenv import load_dotenv  # 小白导读: dotenv 是库，能把 .env 文件里的变量自动注入到环境变量中
import yaml  # 小白导读: yaml 库，用于解析 YAML 格式的配置文件

# 从 .env 文件加载环境变量
# 小白导读: 程序启动时先读 .env，把里面的 KEY=VALUE 对变成系统环境变量
load_dotenv()

# ===== 各服务的 API 密钥 =====
# 小白导读: API Key 是调用第三方服务的"钥匙"，没有它就会被拒绝访问
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')  # OpenAI 大模型的访问密钥
LANGCHAIN_API_KEY = os.getenv('LANGCHAIN_API_KEY')  # LangChain 可观测性平台的密钥
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')  # Firecrawl 网页抓取服务的密钥
# fastCRW：兼容 Firecrawl 的网页抓取器（单二进制，可自托管或云托管）
CRW_API_KEY = os.getenv('CRW_API_KEY')  # fastCRW 服务的访问密钥
# 默认使用云托管；自托管时可覆盖（如 http://localhost:3000）
CRW_API_URL = os.getenv('CRW_API_URL', 'https://fastcrw.com/api')  # fastCRW 服务的请求地址
# 工作目录（数据文件存放位置）
WORKING_DIRECTORY = os.getenv('WORKING_DIRECTORY', './data')  # 项目数据文件的默认存放目录
# Conda 环境名（用于代码执行隔离）
# 小白导读: Conda 是 Python 的环境管理器，不同环境互不干扰，避免依赖冲突
CONDA_ENV = os.getenv('CONDA_ENV', 'base')  # 默认使用 Conda 的 base 环境
# ChromeDriver 路径（Selenium 抓取 Google 搜索结果时使用）
# 小白导读: ChromeDriver 是浏览器的"遥控器"，让代码能自动打开网页、点击按钮
CHROMEDRIVER_PATH = os.getenv('CHROMEDRIVER_PATH', './chromedriver/chromedriver')  # ChromeDriver 可执行文件路径
# 配置目录（agent_models.yaml、agents/、mcp.yaml 的父目录）
CONFIG_DIRECTORY = os.getenv('CONFIG_DIRECTORY', 'config')  # 所有配置文件的根目录


class AgentModelsConfig:
    """从 YAML 文件加载每个 Agent 的模型配置。"""

    def __init__(self, config_path: str = 'config/agent_models.yaml'):
        """初始化：加载 YAML 配置文件。

        Args:
            config_path: YAML 配置文件的路径。

        Raises:
            FileNotFoundError: 配置文件不存在时抛出。
        """
        try:
            # 小白导读: with open(...) 是安全打开文件的方式，读完自动关闭，防止资源泄漏
            with open(config_path, 'r', encoding='utf-8') as file:
                # yaml.safe_load 把 YAML 文本解析成 Python 字典（dict）
                self._config = yaml.safe_load(file)
        except FileNotFoundError as e:
            # 小白导读: 文件找不到时抛出异常，并保留原始错误信息（from e）
            raise FileNotFoundError(f"Configuration file not found: {config_path}") from e

    @property
    def agents(self):
        """获取所有 agents 配置节。"""
        # 小白导读: @property 让方法可以像属性一样调用，不需要加括号
        return self._config.get('agents', {})

    def get_agent_config(self, agent_name: str):
        """获取指定 Agent 的完整配置。"""
        return self.agents.get(agent_name, {})

    def get_provider(self, agent_name: str):
        """获取指定 Agent 的 LLM 供应商名称（如 openai/anthropic）。"""
        agent_config = self.get_agent_config(agent_name)
        return agent_config.get('provider')

    def get_model_config(self, agent_name: str):
        """获取指定 Agent 的模型配置（model、temperature 等）。"""
        agent_config = self.get_agent_config(agent_name)
        return agent_config.get('model_config', {})


# 全局单例：项目启动时加载一次
# 小白导读: 单例模式——整个程序只创建一份配置对象，所有模块共享，节省内存
AGENT_MODELS = AgentModelsConfig(os.path.join(CONFIG_DIRECTORY, 'agent_models.yaml'))