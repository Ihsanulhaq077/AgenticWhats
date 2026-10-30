"""LangGraph assembly: START → classify → route → intent node → guardrails → END."""

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    agent_core, booking_node, cancel_node, classify_node, fallback_node, greeting_node,
    guardrails_node, handoff_node, knowledge_node, order_node, route_after_classify,
    status_node,
)
from app.agents.state import AgentState
from app.agents.tools import ToolContext

_ROUTE_TARGETS = {
    "agent_core", "greeting_node", "order_node", "status_node", "cancel_node",
    "booking_node", "handoff_node", "knowledge_node", "fallback_node",
}


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("classify", classify_node)
    builder.add_node("agent_core", agent_core)
    builder.add_node("greeting_node", greeting_node)
    builder.add_node("order_node", order_node)
    builder.add_node("status_node", status_node)
    builder.add_node("cancel_node", cancel_node)
    builder.add_node("booking_node", booking_node)
    builder.add_node("handoff_node", handoff_node)
    builder.add_node("knowledge_node", knowledge_node)
    builder.add_node("fallback_node", fallback_node)
    builder.add_node("guardrails", guardrails_node)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_after_classify,
        {name: name for name in _ROUTE_TARGETS},
    )
    for name in _ROUTE_TARGETS:
        builder.add_edge(name, "guardrails")
    builder.add_edge("guardrails", END)
    return builder.compile()


agent_graph = build_graph()


def run_agent(ctx: ToolContext, user_message: str) -> dict[str, Any]:
    """Execute the agent graph for one inbound customer message.

    Returns the final state (final_response, intent, tool_calls_log, escalate...).
    """
    initial: dict[str, Any] = {
        "business_id": ctx.business.id,
        "customer_id": ctx.customer.id if ctx.customer else 0,
        "conversation_id": ctx.conversation.id if ctx.conversation else 0,
        "user_message": user_message,
        "tool_calls_log": [],
        "escalate": False,
        "ctx": ctx,  # runtime-only handle, excluded from persisted outputs
    }
    result = agent_graph.invoke(initial, config={"recursion_limit": 12})
    result.pop("ctx", None)
    return result
