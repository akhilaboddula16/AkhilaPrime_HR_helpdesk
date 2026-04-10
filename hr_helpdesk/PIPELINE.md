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
