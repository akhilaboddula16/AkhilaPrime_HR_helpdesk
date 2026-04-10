"""AkhilaPrime HR helpdesk package.

Pipeline order:
  step1_chunking  → split markdown docs into sections
  step2_indexing  → embed chunks and store in pgvector
  step3_retriever → query pgvector for relevant chunks
  step4_app       → Streamlit chat UI (run with streamlit run)
"""
