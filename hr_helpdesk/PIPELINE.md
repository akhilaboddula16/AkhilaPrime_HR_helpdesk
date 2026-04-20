# AkhilaPrime HR Helpdesk — Pipeline Guide

A beginner-friendly breakdown of all six application files and two answer modes.

---

## Architecture Overview

```
                         ┌─────────────────────────────────────┐
                         │        step4_app.py  (UI)           │
                         │                                     │
                         │   ┌──────────┐   ┌──────────────┐  │
                         │   │ Classic  │   │  Agentic RAG │  │
  User Question ─────────►   │  RAG     │   │  (ReAct)     │  │
                         │   └────┬─────┘   └──────┬───────┘  │
                         └────────┼────────────────┼──────────┘
                                  │                │
                    ┌─────────────▼──┐     ┌───────▼────────────────┐
                    │ step3_retriever│     │    step6_agent.py       │
                    │ (single search)│     │  LangGraph ReAct Agent  │
                    └────────┬───────┘     │   ┌─────────────────┐  │
                             │             │   │  step5_tools.py │  │
                             │             │   │  - search_policy│  │
                             │             │   │  - list_policies│  │
                             │             │   │  - get_sections │  │
                             │             │   └────────┬────────┘  │
                             │             └────────────┼───────────┘
                             │                          │  (iterates
                             │                          │   as needed)
                             ▼                          ▼
                         PGVector ◄────── step2_indexing.py ◄── step1_chunking.py
                         (embeddings)    (Gemini Embed)          (markdown docs)
```

---

## File Order

```
hr_helpdesk/
├── step1_chunking.py   ← Step 1 : Read and split HR policy docs
├── step2_indexing.py   ← Step 2 : Embed chunks and store in PGVector
├── step3_retriever.py  ← Step 3 : Retrieve relevant chunks for a query
├── step4_app.py        ← Step 4 : Streamlit chat UI (Classic + Agentic modes)
├── step5_tools.py      ← Step 5 : LangChain Tool wrappers for the agent
└── step6_agent.py      ← Step 6 : LangGraph ReAct agent (Agentic RAG)
```

---

## What Each Step Does

| File | Responsibility |
|---|---|
| `step1_chunking.py` | Reads `.md` files from `docs/` and splits them into section-level chunks. |
| `step2_indexing.py` | Builds LangChain documents, calls Gemini embeddings, stores vectors in PGVector. |
| `step3_retriever.py` | Queries PGVector using MMR → threshold → similarity fallback retrieval. |
| `step4_app.py` | Streamlit UI. Toggle between **Classic RAG** and **Agentic RAG** modes in the sidebar. |
| `step5_tools.py` | Three `@tool`-decorated functions the agent can call: `search_hr_policy`, `list_available_policies`, `get_policy_sections`. |
| `step6_agent.py` | LangGraph `StateGraph` ReAct agent. Thinks → calls tools → observes → repeats → produces a cited final answer with a reasoning trace. |

---

## The Two Answer Modes

### Classic RAG (default)

```
User Question
     │
     ▼
step3_retriever   (single semantic search)
     │
     ▼
Gemini LLM        (one prompt with context)
     │
     ▼
Final Answer + Evidence Pack
```

**Characteristics:** Fast, predictable, one retrieval call per question.

---

### Agentic RAG (toggle ON in sidebar)

```
User Question
     │
     ▼
┌─── Agent Node (Gemini + tools bound) ───────────────────┐
│  Think: "What do I need to search for?"                  │
│     │                                                    │
│     ▼                                                    │
│  Tool Call: search_hr_policy("earned leave days")        │
│     │                                                    │
│     ▼                                                    │
│  Observe: Retrieved 5 policy sections                    │
│     │                                                    │
│     ▼                                                    │
│  Think: "I also need carry-forward rules. Search again." │
│     │                                                    │
│     ▼                                                    │
│  Tool Call: search_hr_policy("leave carry forward rules")│
│     │                                                    │
│     ▼                                                    │
│  Observe: Got more sections                              │
│     │                                                    │
│     ▼                                                    │
│  Think: "I have enough. Draft the final answer."         │
└──────────────────────────────────────────────────────────┘
     │
     ▼
Final Answer + Full Reasoning Trace (visible in UI)
```

**Characteristics:** More thorough, multi-step reasoning, can search multiple times,
shows its thinking, better for complex or multi-part questions.

---

## How to Run

### One-time setup: build the index

```powershell
cd c:\GenAI_questions\agentic-rag_project\AkhilaPrime_HR_
.venv\Scripts\activate
python -m hr_helpdesk.step2_indexing
```

`step2_indexing.py` imports the chunking logic internally, so this covers Steps 1 and 2.

### Start the app

```powershell
streamlit run hr_helpdesk/step4_app.py
```

Then use the **Answer Mode** toggle in the sidebar to switch between Classic RAG and Agentic RAG.

### Test the agent from the CLI

```powershell
python -m hr_helpdesk.step6_agent "How many sick leave days do I get and can I carry them forward?"
```

---

## Neon PostgreSQL Setup Guide

Use Neon for cloud-hosted PostgreSQL with pgvector support.

### Step 1: Create a Neon Account

1. Go to [neon.tech](https://neon.tech/)
2. Sign up with email or GitHub
3. Create a new project

### Step 2: Create a Database

1. In the Neon Console, click **Create Project**
2. Name the project (e.g., `akhilaprime-hr`)
3. Choose a region close to your deployment location
4. Click **Create Project**
5. A default database `neondb` will be created

### Step 3: Get the Connection String

1. In the Neon Console, go to **Connection Details**
2. Select **Connection string** tab
3. Copy the PostgreSQL connection string
4. It will look like:
   ```
   postgresql+psycopg://user:password@ep-xxxxx.us-east-1.neon.tech/neondb?sslmode=require
   ```
5. Change `neondb` to `akhilaprime_hr` if desired

### Step 4: Configure `.env`

1. Open `.env` in your project
2. Set `PGVECTOR_CONNECTION` to your Neon connection string:
   ```env
   PGVECTOR_CONNECTION=postgresql+psycopg://user:password@ep-xxxxx.us-east-1.neon.tech/akhilaprime_hr?sslmode=require
   ```
3. Keep `PGVECTOR_CREATE_EXTENSION=true` (Neon has pgvector pre-installed)

### Step 5: Build the Index

Run indexing to populate your Neon database:

```powershell
python -m hr_helpdesk.step2_indexing
```

This creates tables and loads embeddings to Neon.

### Step 6: Deploy

Your Neon database is now ready for production deployments (Streamlit Cloud, Vercel, Railway, etc.)

---

## Config (`.env`)

### Required Variables

- `GOOGLE_API_KEY`: Your Google Gemini API key (required)
- `PGVECTOR_CONNECTION`: Database connection string (required, see examples below)

### Optional Variables

- `EMBEDDING_MODEL`: defaults to `gemini-embedding-001`
- `CHAT_MODEL`: defaults to `gemini-2.5-flash`
- `HR_DOCS_DIR`: defaults to `docs`
- `HR_COLLECTION_NAME`: defaults to `akhilaprime_hr_helpdesk`
- `EMBEDDING_DIMENSION`: defaults to `1536`
- `PGVECTOR_CREATE_EXTENSION`: defaults to `true`

### Local Development (Docker)

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

### Cloud Deployment (Neon)

```env
GOOGLE_API_KEY=your_google_api_key_here
EMBEDDING_MODEL=gemini-embedding-001
CHAT_MODEL=gemini-2.5-flash
HR_DOCS_DIR=docs
HR_COLLECTION_NAME=akhilaprime_hr_helpdesk
PGVECTOR_CONNECTION=postgresql+psycopg://user:password@ep-xxxxx.us-east-1.neon.tech/akhilaprime_hr?sslmode=require
EMBEDDING_DIMENSION=1536
PGVECTOR_CREATE_EXTENSION=true
```
