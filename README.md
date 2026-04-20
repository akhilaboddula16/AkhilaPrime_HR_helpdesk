# AkhilaPrime HR Helpdesk

This project packages a small RAG-based HR helpdesk for the markdown policy files in `docs/`.

## What it includes

- Markdown-aware section chunking for HR policy documents
- PostgreSQL plus PGVector for vector storage
- Google Gemini embeddings and chat generation
- Streamlit chat UI with two modes:
  - **Classic RAG**: Fast, single-shot retrieval for direct answers.
  - **Agentic RAG**: Multi-step reasoning agent (ReAct) that uses tools to explore policies and self-correct.
- Full source transparency with evidence packs and reasoning traces.

## Project structure

- `docs/`: HR policy source documents
- `hr_helpdesk/step1_chunking.py`: splits markdown files into section chunks
- `hr_helpdesk/step2_indexing.py`: embeds chunks and stores them in PGVector
- `hr_helpdesk/step3_retriever.py`: retrieves relevant chunks for a user query
- `hr_helpdesk/step4_app.py`: Streamlit application (Main UI)
- `hr_helpdesk/step5_tools.py`: LangChain tool definitions for the agent
- `hr_helpdesk/step6_agent.py`: LangGraph ReAct agent for Agentic RAG
- `compose.yaml`: local PostgreSQL plus PGVector setup

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy the sample environment file with `Copy-Item .env.example .env`.
4. Set `GOOGLE_API_KEY` in `.env`.
5. Configure your database:
   - **Neon (Recommended)**: Set `PGVECTOR_CONNECTION` in `.env`.
   - **Local Docker (Optional)**: Run `docker compose up -d`.
6. Build the index with `python -m hr_helpdesk.step2_indexing`.
7. Run the app with `streamlit run hr_helpdesk/step4_app.py`.

## Environment variables

- `GOOGLE_API_KEY`: required
- `EMBEDDING_MODEL`: optional, defaults to `gemini-embedding-001`
- `CHAT_MODEL`: optional, defaults to `gemini-2.5-flash`
- `HR_DOCS_DIR`: optional, defaults to `docs`
- `HR_COLLECTION_NAME`: optional, defaults to `akhilaprime_hr_helpdesk`
- `PGVECTOR_CONNECTION`: required for PGVector, see examples below
- `EMBEDDING_DIMENSION`: optional fixed embedding width
- `PGVECTOR_CREATE_EXTENSION`: optional, defaults to `true`

## Database Options

### Neon PostgreSQL (Cloud - Recommended)

For cloud deployment and easy setup, use [Neon](https://neon.tech/) as a serverless PostgreSQL provider with built-in pgvector support.

1. Sign up at [neon.tech](https://neon.tech/)
2. Create a new project and database
3. Copy your connection string from the Neon dashboard
4. Set `PGVECTOR_CONNECTION` in `.env` to your Neon connection string:

```text
postgresql+psycopg://user:password@ep-xxxxx.us-east-1.neon.tech/akhilaprime_hr?sslmode=require
```

### Local PGVector (Docker - Optional)

If you prefer local development, use the included [compose.yaml](compose.yaml).

```bash
docker compose up -d
docker compose ps
docker compose down
```

Neon automatically enables pgvector, so `PGVECTOR_CREATE_EXTENSION` can remain `true` without issues.
