"""LangGraph agent state (spec §11)."""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Tenant / actor context
    business_id: int
    customer_id: int
    conversation_id: int

    # Input
    user_message: str

    # Understanding
    intent: str
    language: str
    confidence: float

    # Context & tools
    retrieved_context: list[dict]
    tool_calls_log: list[dict]

    # Workflow drafts (multi-turn confirmation)
    draft: dict

    # Output
    final_response: str
    escalate: bool
    error: str | None

    # Runtime-only handle (ToolContext) injected by run_agent(); never persisted.
    ctx: Any
