# studio_entry.py
import sys
import os

# 确保你的项目根目录在 python path 中，防止出现模块找不到的报错
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1. 导入你的顶层门面类
from agent.src.system import MultiAgentSystem

# 2. 模拟最基础的依赖环境初始化
# 注意：在 Studio 开发模式下，checkpointer 必须传入 None！
# 因为 LangGraph Studio 会在底层自动帮你注入一个完全可视化的 Memory 检查点。
# 这样能防止它去和你的生产 Redis 产生冲突和脏数据。
system_instance = MultiAgentSystem(checkpointer=None)

# 3. 剥离并暴露出最纯净的 LangGraph 编译对象给 CLI
# 这对应你类里的 self.graph = self.workflow_manager.get_graph()
app = system_instance.graph