# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 4 — App (Streamlit UI)
# Purpose : The main chat interface. Ties together Steps 1-3:
#           chunks → embeddings → retrieval → Gemini answer → display.
# Run     : streamlit run hr_helpdesk/step4_app.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from __future__ import annotations

import html
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from hr_helpdesk.step1_chunking import iter_markdown_files, split_markdown_sections
from hr_helpdesk.step2_indexing import IndexingConfig, build_vector_store
from hr_helpdesk.step3_retriever import HRRetrievalPipeline, RetrievalConfig

load_dotenv(PROJECT_ROOT / ".env")

# Load Streamlit secrets into environment variables (for cloud deployment)
try:
    for key, value in st.secrets.items():
        os.environ.setdefault(key, str(value))
except Exception:
    pass  # Running locally without secrets

SUGGESTED_PROMPTS = [
    {
        "label": "Leave Rules",
        "question": "How many earned leave, sick leave, casual leave, menstrual leave, and comp off days do employees get, and what are the carry-forward rules?",
        "caption": "Leave balances, carry-forward, and time-off rules.",
    },
    {
        "label": "Payroll Help",
        "question": "What are the salary credit date, payroll cut-off date, payslip access process, and the steps to resolve a salary discrepancy?",
        "caption": "Payroll timelines, payslips, and salary issue resolution.",
    },
    {
        "label": "WFH & Assets",
        "question": "What is the work from home policy, who is eligible for extended remote work, and what equipment or infrastructure support does the company provide?",
        "caption": "Hybrid work, remote eligibility, and equipment support.",
    },
    {
        "label": "Report a Concern",
        "question": "How do employees report a POSH complaint, grievance, or whistleblower concern, and what confidentiality or non-retaliation protections are available?",
        "caption": "POSH, grievance, and whistleblower reporting routes.",
    },
    {
        "label": "Join to Exit",
        "question": "Explain the onboarding, probation, confirmation, resignation, notice period, full and final settlement, and relieving letter process for employees.",
        "caption": "Employee lifecycle guidance from joining to exit.",
    },
]

ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are an HR helpdesk assistant for AkhilaPrime Solutions Pvt. Ltd. "
                "Answer only from the provided policy context. "
                "If the answer is not in the context, say you do not know based on the current policies. "
                "Keep answers practical, specific, and policy-aligned."
            ),
        ),
        ("human", "Context:\n{context}\n\nQuestion: {question}"),
    ]
)


def get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=os.getenv("CHAT_MODEL", "gemini-2.5-flash"))


@st.cache_resource
def get_pipeline() -> HRRetrievalPipeline:
    return HRRetrievalPipeline(RetrievalConfig())


@st.cache_data(show_spinner=False)
def get_library_stats() -> dict[str, str | int]:
    docs_dir = Path(os.getenv("HR_DOCS_DIR", "docs"))
    doc_paths = list(iter_markdown_files(docs_dir))
    section_count = 0
    last_updated = None

    for path in doc_paths:
        section_count += len(split_markdown_sections(path.read_text(encoding="utf-8")))
        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        last_updated = modified_at if last_updated is None or modified_at > last_updated else last_updated

    return {
        "policies": len(doc_paths),
        "sections": section_count,
        "docs_dir": str(docs_dir),
        "last_updated": last_updated.strftime("%d %b %Y") if last_updated else "Unknown",
    }


def has_pgvector_connection() -> bool:
    return bool(os.getenv("PGVECTOR_CONNECTION"))


def has_google_api_key() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


def format_runtime_error(exc: Exception) -> str:
    error_text = str(exc)

    if "API_KEY_SERVICE_BLOCKED" in error_text and "BatchEmbedContents" in error_text:
        return (
            "I could not complete that request because the Google API key in `.env` is blocked from "
            "calling Gemini embeddings. This app needs the `BatchEmbedContents` method for both indexing "
            "and question retrieval.\n\n"
            "Fix:\n"
            "1. Open Google Cloud Console -> APIs & Services -> Credentials.\n"
            "2. Open the API key configured in `.env`.\n"
            "3. Under API restrictions, allow `Generative Language API`, or temporarily set the key to "
            "`Don't restrict key` for testing.\n"
            "4. Save, wait 1 to 2 minutes, then rebuild the index and try again."
        )

    if "SERVICE_DISABLED" in error_text and "generativelanguage.googleapis.com" in error_text:
        return (
            "I could not complete that request because the Generative Language API is not enabled for the "
            "Google project behind the current API key. Enable `Generative Language API`, wait a minute, "
            "then rebuild the index and try again."
        )

    return (
        "I could not complete that request because the policy retrieval layer returned an error. "
        f"Details: {exc}"
    )


def rebuild_index() -> int:
    config = IndexingConfig()
    _, count = build_vector_store(config=config, reset=True)
    get_pipeline.clear()
    return count


def answer_question(question: str) -> tuple[str, list[dict[str, str]], str]:
    pipeline = get_pipeline()
    retrieval_result = pipeline.retrieve(question)
    context = "\n\n".join(doc.page_content for doc in retrieval_result.docs)
    prompt = ANSWER_PROMPT.format(context=context, question=question)
    response = get_llm().invoke(prompt)
    answer = response.content if isinstance(response.content, str) else str(response.content)
    evidence = build_evidence(retrieval_result.docs)
    return answer, evidence, retrieval_result.search_strategy


def build_evidence(docs: list[Document]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for doc in docs:
        section_title = doc.metadata.get("section_title", "Unknown section")
        compact_content = " ".join(doc.page_content.split())
        if compact_content.startswith(section_title):
            compact_content = compact_content[len(section_title):].strip(" -:\n")

        evidence.append(
            {
                "title": doc.metadata.get("title", "Unknown"),
                "section_title": section_title,
                "source": doc.metadata.get("source", "#"),
                "source_label": Path(doc.metadata.get("source", "unknown")).name,
                "excerpt": compact_content[:240] + ("..." if len(compact_content) > 240 else ""),
            }
        )
    return evidence


def init_session_state() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("queued_query", None)


def queue_prompt(prompt: str) -> None:
    st.session_state.queued_query = prompt


def format_html_text(text: str) -> str:
    escaped = html.escape(text.strip())
    return escaped.replace("\n\n", "<br><br>").replace("\n", "<br>")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --fg-ink: #10213b;
            --fg-navy: #1a3159;
            --fg-muted: #5c6b80;
            --fg-panel: rgba(251, 248, 242, 0.92);
            --fg-accent: #c65d33;
            --fg-accent-deep: #9f4420;
            --fg-gold: #b28b44;
            --fg-teal: #0f766e;
            --fg-border: rgba(16, 33, 59, 0.09);
            --fg-shadow: 0 24px 60px rgba(17, 31, 53, 0.12);
            --fg-shadow-soft: 0 14px 34px rgba(17, 31, 53, 0.08);
        }

        @keyframes riseFade {
            from {
                opacity: 0;
                transform: translateY(12px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(198, 93, 51, 0.16), transparent 26%),
                radial-gradient(circle at top right, rgba(15, 118, 110, 0.14), transparent 23%),
                linear-gradient(180deg, #f4ede2 0%, #fbf8f2 38%, #f8f4ec 100%);
            color: var(--fg-ink);
        }

        [data-testid="stAppViewContainer"] > .main {
            background: transparent;
        }

        .block-container {
            max-width: 1200px;
            padding-top: 1.1rem;
            padding-bottom: 2.2rem;
        }

        h1, h2, h3 {
            font-family: Georgia, "Palatino Linotype", serif;
            color: var(--fg-ink);
            letter-spacing: -0.02em;
        }

        p, li, label, div, span {
            font-family: "Trebuchet MS", "Lucida Sans Unicode", sans-serif;
        }

        [data-testid="stSidebar"] {
            background:
                linear-gradient(180deg, rgba(11, 25, 46, 0.98) 0%, rgba(22, 46, 81, 0.98) 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.08);
        }

        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] small,
        [data-testid="stSidebar"] code {
            color: #eef3ff;
        }

        .brand-lockup {
            display: flex;
            align-items: center;
            gap: 0.95rem;
            margin: 0.95rem 0 1rem 0;
        }

        .brand-mark {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 68px;
            height: 68px;
            border-radius: 22px;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(245, 195, 119, 0.18) 100%);
            border: 1px solid rgba(255, 255, 255, 0.18);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), 0 18px 34px rgba(6, 13, 26, 0.24);
            color: #fff0d6;
            font-family: Georgia, "Palatino Linotype", serif;
            font-size: 1.3rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .brand-kicker {
            color: rgba(248, 220, 199, 0.86);
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            margin-bottom: 0.22rem;
        }

        .brand-wordmark {
            font-family: Georgia, "Palatino Linotype", serif;
            font-size: clamp(2.3rem, 5vw, 4.2rem);
            font-weight: 700;
            line-height: 0.96;
            letter-spacing: -0.05em;
            color: white;
        }

        .brand-wordmark span {
            color: #f5c77d;
            text-shadow: 0 0 26px rgba(245, 199, 125, 0.28);
        }

        .brand-subline {
            margin-top: 0.2rem;
            color: rgba(245, 247, 251, 0.82);
            font-size: 0.92rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .hero-brand-lockup {
            margin: 0 0 0.95rem 0;
        }

        .hero-brand-lockup .brand-mark {
            width: 74px;
            height: 74px;
            border-radius: 24px;
            font-size: 1.4rem;
        }

        .hero-brand-lockup .brand-subline {
            color: rgba(245, 247, 251, 0.88);
        }

        .sidebar-brand-card {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.11) 0%, rgba(255, 255, 255, 0.07) 100%);
        }

        .sidebar-brand-card .brand-lockup {
            margin: 0 0 0.7rem 0;
        }

        .sidebar-brand-card .brand-mark {
            width: 56px;
            height: 56px;
            border-radius: 18px;
            font-size: 1.08rem;
        }

        .sidebar-brand-card .brand-wordmark {
            font-size: 2.05rem;
        }

        .sidebar-brand-card .brand-subline {
            color: rgba(249, 223, 205, 0.92);
            font-size: 0.82rem;
        }

        .hero-shell {
            border: 1px solid rgba(255, 255, 255, 0.5);
            border-radius: 28px;
            padding: 2rem;
            margin-bottom: 1.15rem;
            background:
                linear-gradient(135deg, rgba(16, 33, 59, 0.96) 0%, rgba(28, 56, 92, 0.92) 52%, rgba(15, 118, 110, 0.88) 100%);
            box-shadow: var(--fg-shadow);
            color: white;
            animation: riseFade 0.7s ease-out;
        }

        .hero-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.38rem 0.7rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.12);
            color: #f8dbc9;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .hero-title {
            max-width: 720px;
            margin: 1rem 0 0.65rem 0;
            font-size: clamp(2.15rem, 3.4vw, 3.65rem);
            line-height: 1.02;
            color: white;
        }

        .hero-subtitle {
            max-width: 690px;
            color: rgba(244, 245, 250, 0.86);
            font-size: 1rem;
            line-height: 1.6;
            margin-bottom: 1.2rem;
        }

        .hero-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            margin-bottom: 1.45rem;
        }

        .hero-pill {
            padding: 0.5rem 0.8rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.14);
            color: #f7f4ef;
            font-size: 0.88rem;
        }

        .hero-stat-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.9rem;
        }

        .hero-stat-card {
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 1rem 1.05rem;
        }

        .hero-stat-label {
            color: rgba(240, 242, 247, 0.72);
            font-size: 0.82rem;
            margin-bottom: 0.3rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .hero-stat-value {
            font-size: 1.55rem;
            font-weight: 700;
            color: white;
            line-height: 1.1;
        }

        .hero-stat-note {
            margin-top: 0.32rem;
            color: rgba(244, 245, 250, 0.72);
            font-size: 0.88rem;
        }

        .signal-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.95rem;
            margin: 0 0 1.1rem 0;
        }

        .signal-card {
            border-radius: 24px;
            padding: 1.15rem 1.15rem 1.05rem 1.15rem;
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.92) 0%, rgba(250, 246, 239, 0.9) 100%);
            border: 1px solid rgba(16, 33, 59, 0.08);
            box-shadow: var(--fg-shadow-soft);
            animation: riseFade 0.72s ease-out;
        }

        .signal-kicker {
            color: var(--fg-accent);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.74rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }

        .signal-value {
            color: var(--fg-navy);
            font-family: Georgia, "Palatino Linotype", serif;
            font-size: 1.5rem;
            line-height: 1.05;
            margin-bottom: 0.42rem;
        }

        .signal-copy {
            color: var(--fg-muted);
            font-size: 0.92rem;
            line-height: 1.55;
            margin-bottom: 0.75rem;
        }

        .signal-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.34rem 0.68rem;
            background: rgba(16, 33, 59, 0.06);
            border: 1px solid rgba(16, 33, 59, 0.08);
            color: var(--fg-navy);
            font-size: 0.78rem;
            font-weight: 700;
        }

        .section-heading {
            margin: 1.25rem 0 0.55rem 0;
            color: var(--fg-ink);
            font-size: 1.1rem;
            font-weight: 700;
        }

        .workbench-card {
            min-height: 142px;
            border-radius: 22px;
            border: 1px solid var(--fg-border);
            background: var(--fg-panel);
            box-shadow: 0 12px 30px rgba(17, 31, 53, 0.07);
            padding: 1.05rem 1rem;
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
        }

        .workbench-card:hover {
            transform: translateY(-1px);
            box-shadow: 0 16px 34px rgba(17, 31, 53, 0.09);
            border-color: rgba(198, 93, 51, 0.16);
        }

        .workflow-badge {
            display: inline-flex;
            align-items: center;
            margin-bottom: 0.75rem;
            border-radius: 999px;
            padding: 0.32rem 0.62rem;
            background: rgba(16, 33, 59, 0.06);
            border: 1px solid rgba(16, 33, 59, 0.08);
            color: var(--fg-accent);
            font-size: 0.74rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .workbench-title {
            font-family: Georgia, "Palatino Linotype", serif;
            font-size: 1.12rem;
            color: var(--fg-navy);
            margin-bottom: 0.4rem;
        }

        .workbench-copy {
            color: var(--fg-muted);
            font-size: 0.93rem;
            line-height: 1.52;
        }

        .workflow-foot {
            margin-top: 0.85rem;
            color: rgba(20, 43, 74, 0.72);
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.03em;
        }

        .sidebar-card {
            border-radius: 20px;
            padding: 1rem;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            margin-bottom: 0.9rem;
        }

        .sidebar-label {
            color: rgba(239, 242, 255, 0.72);
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.76rem;
            margin-bottom: 0.35rem;
        }

        .sidebar-value {
            color: white;
            font-size: 1.08rem;
            font-weight: 700;
            line-height: 1.35;
        }

        .sidebar-copy {
            color: rgba(239, 242, 255, 0.78);
            font-size: 0.87rem;
            line-height: 1.48;
            margin-top: 0.3rem;
        }

        .sidebar-path {
            display: inline-flex;
            align-items: center;
            margin-left: 0.35rem;
            padding: 0.18rem 0.52rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.16);
            color: #fff0d6;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
        }

        .status-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.7rem;
            margin-top: 0.6rem;
        }

        .status-chip {
            border-radius: 16px;
            padding: 0.8rem 0.85rem;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
        }

        .status-chip strong {
            display: block;
            color: white;
            font-size: 0.95rem;
        }

        .status-chip span {
            color: rgba(239, 242, 255, 0.74);
            font-size: 0.78rem;
        }

        .assistant-panel,
        .user-panel {
            border-radius: 22px;
            padding: 1rem 1.05rem;
            border: 1px solid var(--fg-border);
            box-shadow: 0 12px 32px rgba(17, 31, 53, 0.06);
        }

        .assistant-panel {
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(251, 248, 242, 0.98) 100%);
        }

        .user-panel {
            background: linear-gradient(180deg, rgba(23, 44, 74, 0.95) 0%, rgba(30, 62, 104, 0.92) 100%);
            color: white;
        }

        .message-kicker {
            margin-bottom: 0.55rem;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
        }

        .assistant-panel .message-kicker {
            color: var(--fg-accent);
        }

        .user-panel .message-kicker {
            color: #f7dccf;
        }

        .message-body {
            line-height: 1.68;
            font-size: 0.99rem;
        }

        .assistant-panel .message-body {
            color: var(--fg-ink);
        }

        .user-panel .message-body {
            color: rgba(255, 255, 255, 0.94);
        }

        .meta-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.38rem 0 0.15rem 0;
        }

        .meta-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            padding: 0.38rem 0.7rem;
            background: rgba(16, 33, 59, 0.06);
            color: var(--fg-navy);
            border: 1px solid rgba(16, 33, 59, 0.08);
            font-size: 0.8rem;
            font-weight: 700;
        }

        .evidence-card {
            border-radius: 18px;
            background: rgba(248, 244, 236, 0.9);
            border: 1px solid rgba(16, 33, 59, 0.08);
            padding: 0.95rem 1rem;
            margin-bottom: 0.7rem;
        }

        .evidence-title {
            color: var(--fg-navy);
            font-weight: 700;
            font-size: 0.98rem;
        }

        .evidence-section {
            color: var(--fg-accent);
            font-size: 0.82rem;
            font-weight: 700;
            margin-top: 0.2rem;
        }

        .evidence-copy {
            color: var(--fg-muted);
            line-height: 1.55;
            font-size: 0.9rem;
            margin: 0.5rem 0 0.55rem 0;
        }

        .evidence-source {
            color: var(--fg-gold);
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        .conversation-shell {
            border-radius: 26px;
            padding: 1.15rem 1.2rem;
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.9) 0%, rgba(249, 245, 238, 0.92) 100%);
            border: 1px solid rgba(16, 33, 59, 0.08);
            box-shadow: var(--fg-shadow-soft);
            margin: 0.35rem 0 1rem 0;
        }

        .conversation-kicker {
            color: var(--fg-accent);
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            margin-bottom: 0.35rem;
        }

        .conversation-title {
            color: var(--fg-navy);
            font-family: Georgia, "Palatino Linotype", serif;
            font-size: clamp(1.45rem, 3vw, 2rem);
            line-height: 1.05;
            margin-bottom: 0.42rem;
        }

        .conversation-copy {
            color: var(--fg-muted);
            font-size: 0.95rem;
            line-height: 1.6;
            max-width: 760px;
        }

        .conversation-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.85rem;
        }

        .conversation-chip {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.38rem 0.72rem;
            background: rgba(16, 33, 59, 0.05);
            border: 1px solid rgba(16, 33, 59, 0.08);
            color: var(--fg-navy);
            font-size: 0.8rem;
            font-weight: 700;
        }

        div.stButton > button {
            border-radius: 16px;
            border: 1px solid rgba(16, 33, 59, 0.08);
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(244, 238, 228, 0.96) 100%);
            color: var(--fg-ink);
            font-weight: 700;
            min-height: 3rem;
            box-shadow: 0 8px 22px rgba(17, 31, 53, 0.06);
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
        }

        div.stButton > button:hover {
            border-color: rgba(198, 93, 51, 0.38);
            color: var(--fg-accent-deep);
            transform: translateY(-1px);
            box-shadow: 0 12px 24px rgba(17, 31, 53, 0.08);
        }

        div.stButton > button p,
        div.stButton > button span {
            color: var(--fg-ink) !important;
        }

        div.stButton > button:hover p,
        div.stButton > button:hover span {
            color: var(--fg-accent-deep) !important;
        }

        [data-testid="stSidebar"] div.stButton > button {
            background: linear-gradient(180deg, rgba(255, 248, 240, 0.98) 0%, rgba(240, 231, 220, 0.98) 100%);
            border: 1px solid rgba(255, 255, 255, 0.18);
            color: #162a4a !important;
        }

        [data-testid="stSidebar"] div.stButton > button p,
        [data-testid="stSidebar"] div.stButton > button span {
            color: #162a4a !important;
            font-weight: 700;
        }

        [data-testid="stSidebar"] div.stButton > button:hover {
            background: linear-gradient(180deg, rgba(255, 240, 226, 1) 0%, rgba(247, 224, 205, 1) 100%);
            border-color: rgba(198, 93, 51, 0.46);
        }

        [data-testid="stSidebar"] div.stButton > button:hover p,
        [data-testid="stSidebar"] div.stButton > button:hover span {
            color: #8f3a18 !important;
        }

        [data-testid="stChatInput"] {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(16, 33, 59, 0.08);
            border-radius: 24px;
            padding: 0.25rem 0.35rem;
            box-shadow: 0 14px 34px rgba(17, 31, 53, 0.08);
        }

        [data-testid="stChatInput"] textarea {
            font-size: 0.98rem;
        }

        [data-testid="stExpander"] {
            border-radius: 18px;
            border: 1px solid rgba(16, 33, 59, 0.08);
            overflow: hidden;
            background: rgba(255, 255, 255, 0.55);
        }

        .trust-banner {
            border-radius: 18px;
            padding: 1rem 1.05rem;
            background: rgba(15, 118, 110, 0.08);
            border: 1px solid rgba(15, 118, 110, 0.15);
            color: #0f5b56;
            margin: 0.35rem 0 1rem 0;
        }

        .trust-title {
            color: #0f5b56;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            font-size: 0.78rem;
            margin-bottom: 0.3rem;
        }

        .trust-copy {
            color: #165d57;
            line-height: 1.6;
            max-width: 760px;
        }

        .trust-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.8rem;
        }

        .trust-chip {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.34rem 0.68rem;
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(15, 118, 110, 0.14);
            color: #165d57;
            font-size: 0.78rem;
            font-weight: 700;
        }

        @media (max-width: 900px) {
            .hero-shell {
                padding: 1.35rem;
            }

            .hero-stat-grid,
            .status-grid,
            .signal-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(stats: dict[str, str | int]) -> None:
    st.markdown(
        f"""
        <section class="hero-shell">
            <div class="brand-lockup hero-brand-lockup">
                <div class="brand-mark">AP</div>
                <div>
                    <div class="brand-kicker">AkhilaPrime Solutions Pvt. Ltd.</div>
                    <div class="brand-wordmark">Akhila<span>Prime</span></div>
                    <div class="brand-subline">HR Copilot Signature Experience</div>
                </div>
            </div>
            <div class="hero-eyebrow">Enterprise Policy Intelligence</div>
            <h1 class="hero-title">Policy intelligence that feels boardroom-ready.</h1>
            <p class="hero-subtitle">
                Ask about leave, payroll, conduct, onboarding, exits, insurance, or compliance.
                Every answer is grounded in your indexed HR policy library and surfaced with source transparency.
            </p>
            <div class="hero-pill-row">
                <span class="hero-pill">Gemini answers</span>
                <span class="hero-pill">PGVector retrieval</span>
                <span class="hero-pill">{stats['policies']} policy files</span>
                <span class="hero-pill">{stats['sections']} indexed sections</span>
            </div>
            <div class="hero-stat-grid">
                <div class="hero-stat-card">
                    <div class="hero-stat-label">Policy Coverage</div>
                    <div class="hero-stat-value">{stats['policies']}</div>
                    <div class="hero-stat-note">Markdown policy documents under active coverage.</div>
                </div>
                <div class="hero-stat-card">
                    <div class="hero-stat-label">Search Depth</div>
                    <div class="hero-stat-value">{stats['sections']}</div>
                    <div class="hero-stat-note">Section-level chunks available for grounded retrieval.</div>
                </div>
                <div class="hero-stat-card">
                    <div class="hero-stat-label">Last Content Update</div>
                    <div class="hero-stat-value">{stats['last_updated']}</div>
                    <div class="hero-stat-note">Most recent policy file timestamp in your knowledge base.</div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_signal_grid(stats: dict[str, str | int]) -> None:
    stack_value = "Configured" if has_google_api_key() and has_pgvector_connection() else "Needs attention"
    stack_copy = (
        "Gemini and PGVector routes are configured for policy-grounded conversations."
        if has_google_api_key() and has_pgvector_connection()
        else "One or more runtime settings still need attention before the assistant is fully ready."
    )

    st.markdown(
        f"""
        <section class="signal-grid">
            <article class="signal-card">
                <div class="signal-kicker">Coverage Signal</div>
                <div class="signal-value">{stats['policies']} policy files</div>
                <div class="signal-copy">
                    Your assistant is drawing from a dedicated HR policy estate with section-level indexing for precise retrieval.
                </div>
                <div class="signal-pill">{stats['sections']} searchable sections</div>
            </article>
            <article class="signal-card">
                <div class="signal-kicker">Response Posture</div>
                <div class="signal-value">Grounded only</div>
                <div class="signal-copy">
                    Answers are designed to stay anchored to policy text, cite evidence, and avoid unsupported free-form advice.
                </div>
                <div class="signal-pill">Evidence-backed mode</div>
            </article>
            <article class="signal-card">
                <div class="signal-kicker">Runtime Status</div>
                <div class="signal-value">{stack_value}</div>
                <div class="signal-copy">
                    {stack_copy}
                </div>
                <div class="signal-pill">Last policy update: {stats['last_updated']}</div>
            </article>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(stats: dict[str, str | int]) -> None:
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-card sidebar-brand-card">
                <div class="brand-lockup">
                    <div class="brand-mark">AP</div>
                    <div>
                        <div class="brand-kicker">Operations Console</div>
                        <div class="brand-wordmark">Akhila<span>Prime</span></div>
                        <div class="brand-subline">HR Copilot</div>
                    </div>
                </div>
                <div class="sidebar-copy">
                    Premium internal assistance for policy lookups, compliance guidance, and employee lifecycle support.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Rebuild Knowledge Index", use_container_width=True):
            with st.spinner("Refreshing indexed policy sections..."):
                try:
                    chunk_count = rebuild_index()
                except Exception as exc:
                    st.error(format_runtime_error(exc))
                else:
                    st.success(f"Indexed {chunk_count} sections.")

        if st.button("Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        st.markdown(
            f"""
            <div class="sidebar-card">
                <div class="sidebar-label">Library Snapshot</div>
                <div class="sidebar-value">{stats['policies']} policies | {stats['sections']} sections</div>
                <div class="sidebar-copy">Source directory:<span class="sidebar-path">{stats['docs_dir']}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="status-grid">
                <div class="status-chip">
                    <strong>{'Ready' if has_google_api_key() else 'Missing'}</strong>
                    <span>Gemini API key</span>
                </div>
                <div class="status-chip">
                    <strong>{'Connected' if has_pgvector_connection() else 'Not set'}</strong>
                    <span>PGVector route</span>
                </div>
                <div class="status-chip">
                    <strong>{os.getenv('CHAT_MODEL', 'gemini-2.5-flash')}</strong>
                    <span>Response model</span>
                </div>
                <div class="status-chip">
                    <strong>{os.getenv('EMBEDDING_MODEL', 'gemini-embedding-001')}</strong>
                    <span>Embedding model</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="sidebar-card">
                <div class="sidebar-label">Trust Layer</div>
                <div class="sidebar-copy">
                    Answers are constrained to retrieved policy context and displayed with evidence so employees can verify what the assistant is relying on.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_launchpad() -> None:
    st.markdown('<div class="section-heading">Scenario Launchpad</div>', unsafe_allow_html=True)
    for start in range(0, len(SUGGESTED_PROMPTS), 3):
        prompt_row = SUGGESTED_PROMPTS[start:start + 3]
        columns = st.columns(len(prompt_row), gap="small")
        for column, prompt in zip(columns, prompt_row):
            with column:
                st.markdown(
                    f"""
                    <div class="workbench-card">
                        <div class="workflow-badge">Ready workflow</div>
                        <div class="workbench-title">{prompt['label']}</div>
                        <div class="workbench-copy">{prompt['caption']}</div>
                        <div class="workflow-foot">Preload a polished employee-style question</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"Open {prompt['label']}", key=f"prompt_{prompt['label']}", use_container_width=True):
                    queue_prompt(prompt["question"])
                    st.rerun()


def render_trust_banner() -> None:
    st.markdown(
        """
        <div class="trust-banner">
            <div class="trust-title">Trust Layer</div>
            <div class="trust-copy">
                This assistant is optimized for policy-grounded answers, not free-form HR advice.
                If the policy set does not support an answer, it should say so clearly.
            </div>
            <div class="trust-chip-row">
                <span class="trust-chip">Policy-grounded responses</span>
                <span class="trust-chip">Visible evidence pack</span>
                <span class="trust-chip">No unsupported HR improvisation</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_conversation_header() -> None:
    prompt_count = sum(1 for message in st.session_state.messages if message["role"] == "user")
    title = "Conversation Desk" if prompt_count else "Ask the Policy Library"
    copy = (
        "Review the evidence-backed response stream below. Every answer is paired with retrieval context so teams can verify the source."
        if prompt_count
        else "Start with a launchpad scenario or ask a direct policy question. The assistant will search the indexed HR library before it answers."
    )

    st.markdown(
        f"""
        <section class="conversation-shell">
            <div class="conversation-kicker">Guided Workspace</div>
            <div class="conversation-title">{title}</div>
            <div class="conversation-copy">{copy}</div>
            <div class="conversation-chip-row">
                <span class="conversation-chip">{prompt_count} employee prompts in session</span>
                <span class="conversation-chip">Source transparency enabled</span>
                <span class="conversation-chip">Retrieval-first answer flow</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_messages() -> None:
    for message in st.session_state.messages:
        if message["role"] == "user":
            with st.chat_message("user", avatar=":material/person:"):
                st.markdown(
                    f"""
                    <div class="user-panel">
                        <div class="message-kicker">Employee Request</div>
                        <div class="message-body">{format_html_text(message['content'])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            continue

        with st.chat_message("assistant", avatar=":material/verified_user:"):
            st.markdown(
                f"""
                <div class="assistant-panel">
                    <div class="message-kicker">Grounded Policy Answer</div>
                    <div class="message-body">{format_html_text(message['content'])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                f"""
                <div class="meta-row">
                    <span class='meta-pill'>Retrieval: {html.escape(message['strategy'].upper())}</span>
                    <span class='meta-pill'>Sources: {len(message['evidence'])}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if message["evidence"]:
                with st.expander("Evidence pack", expanded=False):
                    for item in message["evidence"]:
                        st.markdown(
                            f"""
                            <div class="evidence-card">
                                <div class="evidence-title">{html.escape(item['title'])}</div>
                                <div class="evidence-section">{html.escape(item['section_title'])}</div>
                                <div class="evidence-copy">{html.escape(item['excerpt'])}</div>
                                <div class="evidence-source">{html.escape(item['source_label'])} | {html.escape(item['source'])}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )


def process_query(question: str) -> None:
    st.session_state.messages.append({"role": "user", "content": question})

    try:
        with st.status("Consulting the policy library...", expanded=False) as status:
            status.write("Scanning indexed HR sections.")
            answer, evidence, strategy = answer_question(question)
            status.write("Drafting a policy-grounded response.")
            status.update(label="Response ready", state="complete", expanded=False)
    except Exception as exc:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": format_runtime_error(exc),
                "evidence": [],
                "strategy": "unavailable",
            }
        )
        return

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "evidence": evidence,
            "strategy": strategy,
        }
    )


def main() -> None:
    st.set_page_config(
        page_title="AkhilaPrime HR Helpdesk",
        page_icon=":material/policy:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_session_state()
    inject_styles()

    stats = get_library_stats()
    render_sidebar(stats)
    render_hero(stats)
    render_trust_banner()
    render_signal_grid(stats)

    queued_query = st.session_state.pop("queued_query", None)
    if queued_query:
        process_query(queued_query)
        st.rerun()

    if not has_pgvector_connection():
        st.warning("Set `PGVECTOR_CONNECTION` in `.env` before building the index or asking questions.")
        return

    if not has_google_api_key():
        st.warning("Set `GOOGLE_API_KEY` in `.env` before asking questions.")
        return

    if not st.session_state.messages:
        render_launchpad()

    render_conversation_header()
    render_messages()

    submitted_query = st.chat_input(
        "Ask a policy question about leave, payroll, compliance, onboarding, insurance, or exits"
    )
    if submitted_query:
        process_query(submitted_query)
        st.rerun()


if __name__ == "__main__":
    main()
