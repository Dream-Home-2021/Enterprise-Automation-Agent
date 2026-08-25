from langgraph.graph import StateGraph, END, START
from typing import cast

from .state import State
from .node import agent_node, human_choice_node, note_agent_node, human_review_node, refiner_node
from .workflow_router import QualityReview_router, hypothesis_router, process_router, main_router, human_wait_review_router
from ..agents.factory import AgentFactory


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

    def _build_analysis_subgraph(self, checkpointer=None):
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
        

        subgraph.add_node("Hypothesis", _wrap_agent_node(self.agents["hypothesis_agent"], "hypothesis_agent"))
        subgraph.add_node("Process", _wrap_agent_node(self.agents["process_agent"], "process_agent"))
        subgraph.add_node("Visualization", _wrap_agent_node(self.agents["visualization_agent"], "visualization_agent"))
        subgraph.add_node("Search", _wrap_agent_node(self.agents["search_agent"], "search_agent"))
        subgraph.add_node("Coder", _wrap_agent_node(self.agents["code_agent"], "code_agent"))
        subgraph.add_node("Report", _wrap_agent_node(self.agents["report_agent"], "report_agent"))
        subgraph.add_node("QualityReview", _wrap_agent_node(self.agents["quality_review_agent"], "quality_review_agent"))
        subgraph.add_node("NoteTaker", _wrap_note_agent(self.agents["note_agent"], "note_agent"))
        subgraph.add_node("HumanChoice", human_choice_node)
        subgraph.add_node("HumanReview", human_review_node)
        subgraph.add_node("Refiner", _wrap_refiner(self.agents["refiner_agent"], "refiner_agent"))

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

    def _build_chat_subgraph(self):
        """"""
        subgraph = StateGraph(State)
        def _chat_agent_node(agent, name):
            def action(state, config=None, store=None):
                return agent_node(cast(State, state), agent, name)
            return action
        subgraph.add_node("chat_agent", _chat_agent_node(self.agents["chat_agent"], "chat_agent"))
        
        subgraph.add_edge(START, "chat_agent")
        subgraph.add_edge("chat_agent", END)

        return subgraph.compile(name="chat", checkpointer=self.checkpointer)

    def setup_workflow(self, checkpointer=None):
        print(f"[DEBUG] 传入的 checkpointer = {checkpointer}")
        """搭建父图，checkpointer 统一下发给子图。"""
        self.checkpointer = checkpointer

        self.workflow = StateGraph(State)

        analysis_subgraph = self._build_analysis_subgraph(checkpointer=checkpointer)
        chat_subgraph = self._build_chat_subgraph()

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