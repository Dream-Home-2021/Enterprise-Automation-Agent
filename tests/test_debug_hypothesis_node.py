"""侦察测试：用真实参数调用 agent_node，配合断点观察 HypothesisAgent 的执行过程。

调试方法:
    1. 在 src/core/node.py:209 (result = agent.invoke(state)) 下断点
    2. 用调试模式运行本测试（VSCode: Ctrl+Shift+D → "Debug this test"）
    3. 断点命中后按 F11 step into，会走进 HypothesisAgent.invoke

来源: 真实工作流中断点抓取的 State 快照（2026-06-27）
    - datapath: 1122.csv
    - task: Use machine learning to perform data analysis and write complete graphical reports
"""

from langchain_core.messages import HumanMessage

from src.core.state import State
from src.core.node import agent_node
from src.core.language_models import LanguageModelManager
from src.agents.hypothesis_agent import HypothesisAgent


def test_debug_hypothesis_node():
    # --- 真实 State 快照（来自你断点抓取的数据） ---
    state = State(
        messages=[
            HumanMessage(
                content=(
                    "\n        datapath:1122.csv\n"
                    "        Use machine learning to perform data analysis"
                    " and write complete graphical reports\n        "
                )
            )
        ],
        last_active_agent="user",
        step_count=0,
        todo_list=[],
        completed_tasks=[],
        search_artifacts={},
        data_viz_artifacts={},
        code_artifacts={},
        report_artifacts={},
        needs_revision=False,
        revision_count=0,
        # 以下字段都是默认值，显式写出来方便调试时对照：
        # current_instruction=None, next_workflow_step=None,
        # hypothesis=None, quality_feedback=None,
    )

    # --- 真实 HypothesisAgent ---
    llm_manager = LanguageModelManager()
    agent = HypothesisAgent(
        language_model_manager=llm_manager,
        team_members=["hypothesis_agent"],
    )

    # --- 调用：断点会命中 node.py:209 的 agent.invoke(state) ---
    result = agent_node(state, agent, "hypothesis_agent")

    # --- 基础断言（确认节点跑通了） ---
    assert result["last_active_agent"] == "hypothesis_agent"
    assert result["step_count"] == 1
    assert "messages" in result
    # HypothesisAgent 会写 hypothesis 字段
    print("hypothesis result:", result.get("hypothesis"))


if __name__ == "__main__":
    test_debug_hypothesis_node()
    print("PASS")
