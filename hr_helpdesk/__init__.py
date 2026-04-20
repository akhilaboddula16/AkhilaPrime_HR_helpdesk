"""AkhilaPrime HR helpdesk — Agentic RAG package.

Pipeline order:
  step1_chunking  → split markdown docs into sections
  step2_indexing  → embed chunks and store in pgvector
  step3_retriever → query pgvector for relevant chunks  (Classic RAG)
  step4_app       → Streamlit chat UI (run with: streamlit run hr_helpdesk/step4_app.py)
  step5_tools     → LangChain Tool wrappers for the agent
  step6_agent     → LangGraph ReAct agent (Agentic RAG)

Mode selection is done at runtime via the sidebar toggle in step4_app.py:
  - Classic RAG  : step3_retriever → Gemini (single-shot)
  - Agentic RAG  : step6_agent (ReAct loop, multi-tool, reasoning trace)
"""
