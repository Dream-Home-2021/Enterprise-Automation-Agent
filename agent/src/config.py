import os
from dotenv import load_dotenv
import yaml

# 从 .env 文件加载环境变量

load_dotenv()


OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
LANGCHAIN_API_KEY = os.getenv('LANGCHAIN_API_KEY')
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY')
CRW_API_KEY = os.getenv('CRW_API_KEY')
CRW_API_URL = os.getenv('CRW_API_URL', 'https://fastcrw.com/api')
WORKING_DIRECTORY = os.getenv('WORKING_DIRECTORY', './data')

CONDA_ENV = os.getenv('CONDA_ENV', 'base')

CHROMEDRIVER_PATH = os.getenv('CHROMEDRIVER_PATH', './chromedriver/chromedriver')
CONFIG_DIRECTORY = os.getenv('CONFIG_DIRECTORY', 'config')


class AgentModelsConfig:
    """ YAML  Agent """

    def __init__(self, config_path: str = 'config/agent_models.yaml'):
        """ YAML 

        Args:
            config_path: YAML 配置文件的路径。

        Raises:
            FileNotFoundError: 配置文件不存在时抛出。
        """
        try:

            with open(config_path, 'r', encoding='utf-8') as file:
                self._config = yaml.safe_load(file)
        except FileNotFoundError as e:

            raise FileNotFoundError(f"Configuration file not found: {config_path}") from e

    @property
    def agents(self):
        """ agents """

        return self._config.get('agents', {})

    def get_agent_config(self, agent_name: str):
        """ Agent """
        return self.agents.get(agent_name, {})

    def get_provider(self, agent_name: str):
        """ Agent  LLM  openai/anthropic"""
        agent_config = self.get_agent_config(agent_name)
        return agent_config.get('provider')

    def get_model_config(self, agent_name: str):
        """ Agent modeltemperature """
        agent_config = self.get_agent_config(agent_name)
        return agent_config.get('model_config', {})


# 全局单例：项目启动时加载一次

AGENT_MODELS = AgentModelsConfig(os.path.join(CONFIG_DIRECTORY, 'agent_models.yaml'))