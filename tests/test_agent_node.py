def test_agent_node_real_agent():
    """用真实 State + 真实 SearchAgent 调用 agent_node。

    调试方法:
    1. 在 src/core/node.py:209 (result = agent.invoke(state)) 下断点
    2. 调试模式运行本测试
    3. 断点命中后按 F11 step into，会走进 base.py 的 SearchAgent.invoke
    """
    from src.core.node import agent_node
    from src.core.state import State
    from src.core.language_models import LanguageModelManager
    from src.agents.search_agent import SearchAgent
    from langchain_core.messages import HumanMessage

    # 真实 State
    state = State(
        messages=[HumanMessage(content="请分析量子计算")],
        step_count=2,
    )

    # 真实 BaseAgent 子类
    llm_manager = LanguageModelManager()
    agent = SearchAgent(
        language_model_manager=llm_manager,
        team_members=["search_agent"],
    )

    # 真实 name
    name = "search_agent"

    # 调用 —— 断点会命中 agent.invoke(state)
    result = agent_node(state, agent, name)

    # 基础断言
    assert result["last_active_agent"] == name
    assert result["step_count"] == 3


if __name__ == "__main__":
    test_agent_node_real_agent()
    print("PASS")
