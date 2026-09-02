from langgraph.graph import StateGraph, END, START
from typing import cast

from ..state import State
from ..node import agent_node

def build_chat_graph(agents: dict, checkpointer=None):
    subgraph = StateGraph(State)
    def _chat_agent_node(agent, name):
        def action(state, config=None, store=None):
            return agent_node(cast(State, state), agent, name)
        return action
    subgraph.add_node("chat_agent", _chat_agent_node(agents["chat_agent"], "chat_agent"))
    
    subgraph.add_edge(START, "chat_agent")
    subgraph.add_edge("chat_agent", END)

    return subgraph.compile(name="chat", checkpointer=checkpointer)
