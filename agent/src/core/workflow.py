from langgraph.graph import StateGraph, END, START
from typing import cast

from .state import State
from .workflow_router import main_router
from ..agents.factory import AgentFactory
from .workflows import build_analysis_graph, build_chat_graph



class WorkflowManager:
    def __init__(self, lm_manager, working_directory, checkpointer=None):
        self.lm_manager = lm_manager
        self.working_directory = working_directory
        self.workflow = None
        self.graph = None
        self.members = [
            "Hypothesis", "Process", "Visualization", "Search", "Coder",
            "Report", "QualityReview", "note", "Refiner", "Chat",
        ]
        self.agents = self.create_agents()
        self.setup_workflow(checkpointer=checkpointer)

    def create_agents(self):
        agents = {}
        factory = AgentFactory(
            language_model_manager=self.lm_manager,
            team_members=self.members,
            working_directory=self.working_directory,
        )
        agents["hypothesis_agent"] = factory.create_agent("hypothesis_agent")
        agents["process_agent"] = factory.create_agent("process_agent")
        agents["visualization_agent"] = factory.create_agent("visualization_agent")
        agents["code_agent"] = factory.create_agent("code_agent")
        agents["search_agent"] = factory.create_agent("search_agent")
        agents["report_agent"] = factory.create_agent("report_agent")
        agents["quality_review_agent"] = factory.create_agent("quality_review_agent")
        agents["note_agent"] = factory.create_agent("note_agent")
        agents["refiner_agent"] = factory.create_agent("refiner_agent")
        agents["chat_agent"] = factory.create_agent("chat_agent")
        return agents

    def _create_model(self, agent_name: str):
        provider = self.lm_manager.get_provider(agent_name)
        model_class = provider.get_model_class()
        config = self.lm_manager.get_model_config(agent_name)
        return model_class(**config)

    def setup_workflow(self, checkpointer=None):
        print(f"[DEBUG] 传入的 checkpointer = {checkpointer}")
        """搭建父图，checkpointer 统一下发给子图。"""
        self.checkpointer = checkpointer

        self.workflow = StateGraph(State)

        analysis_subgraph = build_analysis_graph(self.agents, checkpointer=checkpointer)
        chat_subgraph = build_chat_graph(self.agents, checkpointer=checkpointer)

        self.workflow.add_node("Analysis", analysis_subgraph)
        self.workflow.add_node("Chat", chat_subgraph)

        self.workflow.add_conditional_edges(
            START,
            main_router,
            {"Analysis": "Analysis", "Chat": "Chat"},
        )

        self.workflow.add_edge("Analysis", END)
        self.workflow.add_edge("Chat", END)

        self.graph = self.workflow.compile(checkpointer=checkpointer)

    def get_graph(self):
        return self.graph