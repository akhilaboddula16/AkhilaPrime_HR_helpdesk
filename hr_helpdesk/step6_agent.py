# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 6 — Agentic RAG (LangGraph ReAct Agent)
# Purpose : Replace the single-shot retrieve→LLM pipeline with a
#           reasoning agent that autonomously decides WHICH tools to call,
#           HOW MANY times, and in WHAT ORDER before producing a final
#           grounded, policy-cited answer.
#
# Architecture:
#   User Question
#       ↓
#   [Agent Node] ── think ──► [Tool Node: search_hr_policy]
#       ↑                     [Tool Node: list_available_policies]
#       └──── observe ────── [Tool Node: get_policy_sections]
#       ↓
#   Final Answer (with full reasoning trace)
#
# Run     : python -m hr_helpdesk.step6_agent "How many sick leaves do I get?"
# Next    : step4_app.py calls run_agent() for the agentic chat mode.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from hr_helpdesk.step5_tools import HR_AGENT_TOOLS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structured result returned to the Streamlit UI
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    question: str
    final_answer: str
    reasoning_steps: list[dict[str, Any]] = field(default_factory=list)
    tool_calls_made: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    iterations: int = 0


# ---------------------------------------------------------------------------
# System prompt — tells the LLM how to reason as an HR agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert HR policy assistant for AkhilaPrime Solutions Pvt. Ltd.

Your job is to answer employee HR questions accurately and completely by:
1. THINKING about what information you need to answer the question.
2. SEARCHING the HR policy library using the available tools (you may call tools multiple times with different queries).
3. SYNTHESIZING a final answer that is:
   - Grounded ONLY in the retrieved policy text.
   - Specific, practical, and complete.
   - Accompanied by the exact policy name and section where the information came from.

Available tools:
- search_hr_policy: Semantic search across all policies. Call multiple times with different phrasings if needed.
- list_available_policies: See all policy documents in the knowledge base.
- get_policy_sections: Explore section headings of a specific policy document.

Rules:
- NEVER make up policy details that are not in the retrieved context.
- If the answer is not found after thorough searching, say so explicitly.
- If the question covers multiple topics (e.g. leave AND payroll), search for each topic separately.
- Cite specific policy names and section titles in your final answer.
"""


# ---------------------------------------------------------------------------
# Helper: extract text from message content (handles str, list, None)
# ---------------------------------------------------------------------------

def _extract_text_content(content: Any) -> str:
    """Extract plain text from message content, which may be str, list, or None."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text", "")
                if text and isinstance(text, str):
                    text_parts.append(text.strip())
            elif isinstance(part, str):
                text_parts.append(part.strip())
        return " ".join(text_parts).strip()
    return str(content).strip()


# ---------------------------------------------------------------------------
# Public API — called by step4_app.py
# ---------------------------------------------------------------------------

def run_agent(
    question: str,
    chat_model: str | None = None,
    max_iterations: int = 8,
) -> AgentResult:
    """
    Run the ReAct agent on a user question and return a structured AgentResult.

    Parameters
    ----------
    question     : The employee's HR question.
    chat_model   : Override the LLM model name (defaults to CHAT_MODEL env var).
    max_iterations: Safety cap on reasoning iterations (default 8).

    Returns
    -------
    AgentResult with final_answer, reasoning_steps, tool_calls_made, sources.
    """
    model_name = chat_model or os.getenv("CHAT_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(model=model_name)

    # Use langgraph's built-in create_react_agent — it handles Gemini's
    # message format requirements (alternating roles, non-empty content,
    # system instructions) correctly out of the box.
    agent = create_react_agent(
        model=llm,
        tools=HR_AGENT_TOOLS,
        prompt=SYSTEM_PROMPT,
    )

    initial_state = {
        "messages": [HumanMessage(content=question)],
    }

    # Stream events and collect the full reasoning trace
    reasoning_steps: list[dict[str, Any]] = []
    tool_calls_made: list[dict[str, Any]] = []
    sources: set[str] = set()
    iterations = 0
    final_messages: list[BaseMessage] = []

    # Run with recursion limit as safety cap
    config = {"recursion_limit": max_iterations * 2 + 2}

    try:
        for chunk in agent.stream(initial_state, config=config):
            iterations += 1

            for node_name, node_output in chunk.items():
                messages: list[BaseMessage] = node_output.get("messages", [])
                final_messages = messages

                for msg in messages:
                    if isinstance(msg, AIMessage):
                        # Capture reasoning / thoughts
                        text_content = _extract_text_content(msg.content)
                        if text_content:
                            reasoning_steps.append({
                                "type": "thought",
                                "node": node_name,
                                "content": text_content,
                            })

                        # Capture tool call decisions
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                tool_calls_made.append({
                                    "tool": tc["name"],
                                    "args": tc["args"],
                                })
                                reasoning_steps.append({
                                    "type": "tool_call",
                                    "node": node_name,
                                    "tool": tc["name"],
                                    "args": tc["args"],
                                })

                    elif isinstance(msg, ToolMessage):
                        # Capture tool results and extract source filenames
                        content_str = _extract_text_content(msg.content) or str(msg.content)
                        reasoning_steps.append({
                            "type": "tool_result",
                            "node": node_name,
                            "tool": getattr(msg, "name", "unknown"),
                            "content": content_str[:1500] + ("..." if len(content_str) > 1500 else ""),
                        })

                        # Extract source filenames from the tool output
                        for line in content_str.splitlines():
                            if line.strip().startswith("Source file:"):
                                src = line.split(":", 1)[-1].strip()
                                if src:
                                    sources.add(src)
    except Exception as exc:
        logger.error("Agent execution error: %s", exc, exc_info=True)
        raise

    # Extract the final answer from the last AIMessage that has content but no tool_calls
    final_answer = "I was unable to generate a response. Please try again."
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage):
            text_content = _extract_text_content(msg.content)
            if text_content and not (hasattr(msg, "tool_calls") and msg.tool_calls):
                final_answer = text_content
                break

    return AgentResult(
        question=question,
        final_answer=final_answer,
        reasoning_steps=reasoning_steps,
        tool_calls_made=tool_calls_made,
        sources=sorted(sources),
        iterations=iterations,
    )


# ---------------------------------------------------------------------------
# CLI entry point for quick testing
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="AkhilaPrime HR Agentic RAG — CLI")
    parser.add_argument("question", nargs="?", default="How many earned leave days do employees get?")
    parser.add_argument("--model", default=None, help="Override CHAT_MODEL")
    parser.add_argument("--max-iter", type=int, default=8)
    args = parser.parse_args()

    print(f"\n{'━' * 60}")
    print(f"  AGENTIC HR HELPDESK")
    print(f"{'━' * 60}")
    print(f"  Question: {args.question}")
    print(f"{'━' * 60}\n")

    result = run_agent(args.question, chat_model=args.model, max_iterations=args.max_iter)

    print("REASONING TRACE:")
    for i, step in enumerate(result.reasoning_steps, 1):
        step_type = step["type"].upper()
        if step_type == "THOUGHT":
            print(f"\n  [{i}] 💭 THOUGHT:\n      {step['content'][:300]}")
        elif step_type == "TOOL_CALL":
            print(f"\n  [{i}] 🔧 TOOL CALL: {step['tool']}({step['args']})")
        elif step_type == "TOOL_RESULT":
            preview = step["content"][:200].replace("\n", " ")
            print(f"\n  [{i}] 📄 TOOL RESULT from {step['tool']}:\n      {preview}...")

    print(f"\n{'━' * 60}")
    print("FINAL ANSWER:")
    print(f"{'━' * 60}")
    print(result.final_answer)

    if result.sources:
        print(f"\nSources: {', '.join(result.sources)}")
    print(f"Iterations: {result.iterations} | Tool calls: {len(result.tool_calls_made)}")


if __name__ == "__main__":
    main()
