"""LangGraph agent definition using create_react_agent."""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import get_system_prompt
from app.agent.tools import ALL_TOOLS
from app.config import settings
from app.memory.checkpointer import get_checkpointer

_agent = None


def build_agent():
    """Build (or return cached) LangGraph ReAct agent."""
    global _agent
    if _agent is not None:
        return _agent

    llm = ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=60,
        max_retries=3,
    )

    _agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=get_system_prompt(),
        checkpointer=get_checkpointer(),
    )
    return _agent


def run_agent(user_input: str, thread_id: str = "hyperagent-main") -> str:
    """Synchronously invoke the agent and return the final assistant message."""
    agent = build_agent()
    response = agent.invoke(
        {"messages": [("user", user_input)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    # The last message in the result is the assistant's final output
    return response["messages"][-1].content
