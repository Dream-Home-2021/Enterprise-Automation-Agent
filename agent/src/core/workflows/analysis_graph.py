from langgraph.graph import StateGraph, END, START
from typing import cast

from ..state import State
from ..node import agent_node, human_choice_node, note_agent_node, human_review_node, refiner_node
from ..workflow_router import QualityReview_router, hypothesis_router, process_router, human_wait_review_router

def build_analysis_graph(agents: dict, checkpointer=None):
    """Hypothesis → ... → HumanReview"""
    subgraph = StateGraph(State)

    def _wrap_agent_node(agent, name):
        def action(state, config=None, store=None):
            return agent_node(cast(State, state), agent, name)
        return action

    def _wrap_note_agent(agent, name):
        def action(state, config=None, store=None):
            return note_agent_node(cast(State, state), agent, name)
        return action

    def _wrap_refiner(agent, name):
        def action(state, config=None, store=None):
            return refiner_node(cast(State, state), agent, name)
        return action
    

    subgraph.add_node("Hypothesis", _wrap_agent_node(agents["hypothesis_agent"], "hypothesis_agent"))
    subgraph.add_node("Process", _wrap_agent_node(agents["process_agent"], "process_agent"))
    subgraph.add_node("Visualization", _wrap_agent_node(agents["visualization_agent"], "visualization_agent"))
    subgraph.add_node("Search", _wrap_agent_node(agents["search_agent"], "search_agent"))
    subgraph.add_node("Coder", _wrap_agent_node(agents["code_agent"], "code_agent"))
    subgraph.add_node("Report", _wrap_agent_node(agents["report_agent"], "report_agent"))
    subgraph.add_node("QualityReview", _wrap_agent_node(agents["quality_review_agent"], "quality_review_agent"))
    subgraph.add_node("NoteTaker", _wrap_note_agent(agents["note_agent"], "note_agent"))
    subgraph.add_node("HumanChoice", human_choice_node)
    subgraph.add_node("HumanReview", human_review_node)
    subgraph.add_node("Refiner", _wrap_refiner(agents["refiner_agent"], "refiner_agent"))

    subgraph.add_edge(START, "Hypothesis")
    subgraph.add_edge("Hypothesis", "HumanChoice")

    subgraph.add_conditional_edges(
        "HumanChoice",
        hypothesis_router,
        {"Hypothesis": "Hypothesis", "Process": "Process"},
    )

    subgraph.add_conditional_edges(
        "Process",
        process_router,
        {
            "Coder": "Coder",
            "Search": "Search",
            "Visualization": "Visualization",
            "Report": "Report",
            "Process": "Process",
            "Refiner": "Refiner",
        },
    )

    for member in ["Visualization", "Search", "Coder", "Report"]:
        subgraph.add_edge(member, "QualityReview")

    subgraph.add_conditional_edges(
        "QualityReview",
        QualityReview_router,
        {
            "Visualization": "Visualization",
            "Search": "Search",
            "Coder": "Coder",
            "Report": "Report",
            "NoteTaker": "NoteTaker",
        },
    )

    subgraph.add_edge("NoteTaker", "Process")
    subgraph.add_edge("Refiner", "HumanReview")

    # HumanReview 使用 interrupt() 暂停，恢复后根据 needs_revision 路由
    subgraph.add_conditional_edges(
        "HumanReview",
        human_wait_review_router,
        {"Process": "Process", "END": END},
    )

    return subgraph.compile(name="analysis", checkpointer=checkpointer)
