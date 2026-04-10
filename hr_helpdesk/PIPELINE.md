# AkhilaPrime HR Helpdesk Pipeline Guide

A beginner-friendly breakdown of the four application files and the order they run in.

## File order

```text
hr_helpdesk/
|-- step1_chunking.py    <- Step 1: Read and split HR policy docs
|-- step2_indexing.py    <- Step 2: Embed chunks and store them in PGVector
|-- step3_retriever.py   <- Step 3: Retrieve relevant chunks for a query
`-- step4_app.py         <- Step 4: Streamlit chat UI
```

## How to run

### One-time setup: build the index

```powershell
cd D:\AkhilaPrime_HR
python -m hr_helpdesk.step2_indexing
```

`step2_indexing.py` imports the chunking logic internally, so this covers Steps 1 and 2.

### Start the app

```powershell
streamlit run hr_helpdesk/step4_app.py
```

## What each step does

| File | Responsibility |
| --- | --- |
| `step1_chunking.py` | Reads `.md` files from `docs/` and splits them into section-level chunks. |
| `step2_indexing.py` | Builds LangChain documents, calls Gemini embeddings, and stores vectors in PGVector. |
| `step3_retriever.py` | Queries PGVector using MMR first, then threshold or similarity fallback retrieval. |
| `step4_app.py` | Runs the Streamlit UI, retrieves context, sends prompts to Gemini, and shows evidence-backed answers. |

## Config (`.env`)

```env
GOOGLE_API_KEY=your_google_api_key_here
EMBEDDING_MODEL=gemini-embedding-001
CHAT_MODEL=gemini-2.5-flash
HR_DOCS_DIR=docs
HR_COLLECTION_NAME=akhilaprime_hr_helpdesk
PGVECTOR_CONNECTION=postgresql+psycopg://postgres:postgres@localhost:5433/akhilaprime_hr
EMBEDDING_DIMENSION=1536
PGVECTOR_CREATE_EXTENSION=true
```
