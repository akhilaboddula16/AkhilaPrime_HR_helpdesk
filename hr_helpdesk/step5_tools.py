# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 5 — Agent Tools
# Purpose : Expose HR policy retrieval as LangChain Tool objects so the
#           ReAct agent in step6_agent.py can reason about which tool to
#           call, how many times, and with what query.
# Next    : step6_agent.py builds the LangGraph ReAct agent using these.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from hr_helpdesk.step1_chunking import iter_markdown_files, policy_title_from_path, split_markdown_sections
from hr_helpdesk.step3_retriever import HRRetrievalPipeline, RetrievalConfig

# ---------------------------------------------------------------------------
# Shared retriever singleton (lazy-initialized per process)
# ---------------------------------------------------------------------------

_pipeline: HRRetrievalPipeline | None = None


def _get_pipeline() -> HRRetrievalPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = HRRetrievalPipeline(RetrievalConfig())
    return _pipeline


def reset_pipeline() -> None:
    """Call after rebuilding the index so the next query picks up fresh embeddings."""
    global _pipeline
    _pipeline = None


# ---------------------------------------------------------------------------
# Tool 1 — Semantic search across the full policy library
# ---------------------------------------------------------------------------

@tool
def search_hr_policy(
    query: Annotated[str, "A concise natural-language question or keyword phrase to search the HR policy library."],
    top_k: Annotated[int, "Number of policy sections to return (1-10). Default is 5."] = 5,
) -> str:
    """Search the AkhilaPrime HR policy library for relevant sections.

    Use this tool whenever the employee's question is about company policy,
    leave rules, payroll, onboarding, conduct, benefits, insurance, or exits.
    Returns the most relevant policy text sections with their source file and
    section title so you can ground your answer in evidence.

    Prefer calling this tool multiple times with different query phrasings when
    the first result set seems incomplete or ambiguous.
    """
    top_k = max(1, min(10, top_k))
    pipeline = _get_pipeline()
    result = pipeline.retrieve(query)
    docs = result.docs[:top_k]

    if not docs:
        return "No relevant policy sections found for this query. Try rephrasing or use list_available_policies to check what topics are covered."

    parts: list[str] = [
        f"[Search strategy used: {result.search_strategy.upper()}]\n"
        f"Found {len(docs)} relevant section(s) for query: '{query}'\n"
    ]
    for i, doc in enumerate(docs, 1):
        title = doc.metadata.get("title", "Unknown Policy")
        section = doc.metadata.get("section_title", "Unknown Section")
        source = doc.metadata.get("filename", "unknown.md")
        parts.append(
            f"--- Section {i} ---\n"
            f"Policy: {title}\n"
            f"Section: {section}\n"
            f"Source file: {source}\n"
            f"Content:\n{doc.page_content}\n"
        )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tool 2 — List all available policy documents
# ---------------------------------------------------------------------------

@tool
def list_available_policies() -> str:
    """List all HR policy documents currently indexed in the knowledge base.

    Use this tool when:
    - The employee asks what topics or policies are available.
    - You are unsure whether a specific policy exists before searching it.
    - You want to verify coverage before saying a policy does not exist.

    Returns a numbered list of policy document titles.
    """
    docs_dir = Path(os.getenv("HR_DOCS_DIR", "docs"))
    paths = list(iter_markdown_files(docs_dir))
    if not paths:
        return "No policy documents found in the knowledge base directory."

    lines = [f"Available HR policy documents ({len(paths)} total):\n"]
    for i, path in enumerate(paths, 1):
        title = policy_title_from_path(path)
        lines.append(f"  {i:2}. {title}  ({path.name})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3 — Retrieve all section headings from one specific policy file
# ---------------------------------------------------------------------------

@tool
def get_policy_sections(
    policy_filename: Annotated[
        str,
        "Exact filename of the policy document (e.g. 'Leave_Policy.md'). "
        "Use list_available_policies first if you are unsure of the filename.",
    ],
) -> str:
    """Get the table-of-contents (all section headings) for a specific HR policy file.

    Use this tool when:
    - The employee references a specific policy by name and you want to understand
      its structure before searching individual sections.
    - You need to confirm which sections exist within a policy before
      searching them with search_hr_policy.

    Returns the list of section headings with a short preview of each section.
    """
    docs_dir = Path(os.getenv("HR_DOCS_DIR", "docs"))
    target = docs_dir / policy_filename

    if not target.exists():
        # Try case-insensitive match
        matches = [p for p in iter_markdown_files(docs_dir) if p.name.lower() == policy_filename.lower()]
        if not matches:
            return (
                f"Could not find '{policy_filename}' in the policy library. "
                "Use list_available_policies to see all available filenames."
            )
        target = matches[0]

    markdown_text = target.read_text(encoding="utf-8")
    chunks = split_markdown_sections(markdown_text)
    policy_title = policy_title_from_path(target)

    if not chunks:
        return f"No sections found in '{policy_filename}'. The file may be empty or unstructured."

    lines = [f"Sections in '{policy_title}' ({len(chunks)} sections):\n"]
    for chunk in chunks:
        preview = " ".join(chunk.content.split())[:120]
        if len(" ".join(chunk.content.split())) > 120:
            preview += "..."
        lines.append(f"  • {chunk.title}\n    Preview: {preview}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool registry — imported by step6_agent.py
# ---------------------------------------------------------------------------

HR_AGENT_TOOLS = [
    search_hr_policy,
    list_available_policies,
    get_policy_sections,
]
