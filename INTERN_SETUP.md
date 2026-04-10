# AkhilaPrime HR Helpdesk: Junior Intern Setup Guide

This guide is written for someone with little or no project setup experience.

All commands below are for Windows PowerShell.

## 1. What the project does

This project is a Streamlit HR helpdesk app.

It:
- reads HR policy files from the `docs/` folder
- creates vector embeddings for those documents
- stores them in PostgreSQL plus PGVector
- uses Google Gemini to answer HR questions
- shows the app in a browser with Streamlit

## 2. Things to install first

Before running the project, make sure the laptop has:

1. Python 3.10 or newer
2. Docker Desktop
3. PowerShell
4. Internet access

## 2A. Important: what belongs to the intern

The intern must run everything on his own laptop.

He should use:

- his own local project folder copy
- his own Python virtual environment
- his own `.env` file
- his own Docker Desktop
- his own local PostgreSQL plus PGVector container

He should not use:

- your laptop
- your running Docker container
- your Python environment
- your already-running Streamlit app

In short:

- he must create and run Docker locally on his laptop
- he must create his own `.venv`
- he must keep his own `.env`

## 3. Things to check before running

The intern must ensure:

1. Docker Desktop is open and fully running
2. The project folder is available locally
3. The `.env` file exists
4. `GOOGLE_API_KEY` in `.env` is valid
5. The Google key is allowed to use Generative Language API
6. Port `5433` is not blocked by another database
7. Port `8501` is free, or another Streamlit port is chosen
8. He is running commands on his own laptop, not yours

## 4. First-time setup commands

Open PowerShell and run:

```powershell
cd D:\AkhilaPrime_HR
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Then open `.env` and set:

```env
GOOGLE_API_KEY=your_google_api_key_here
```

## 5. Start the database

This database must run on the intern's own laptop through his own Docker Desktop.

If this is the first time on that laptop:

```powershell
cd D:\AkhilaPrime_HR
docker compose up -d
```

If the container already exists:

```powershell
cd D:\AkhilaPrime_HR
docker start akhilaprime-hr-pgvector
```

To check the database status:

```powershell
docker ps -a --filter name=akhilaprime-hr-pgvector
```

## 6. Build the index

Run:

```powershell
cd D:\AkhilaPrime_HR
.\.venv\Scripts\python.exe hr_helpdesk\step2_indexing.py
```

If indexing works, it should show a line similar to:

```text
Indexed 479 chunks from docs into akhilaprime_hr_helpdesk ...
```

## 7. Run the app

Use:

```powershell
cd D:\AkhilaPrime_HR
.\.venv\Scripts\python.exe -m streamlit run hr_helpdesk\main.py
```

Then open:

```text
http://localhost:8501
```

If port `8501` is busy:

```powershell
.\.venv\Scripts\python.exe -m streamlit run hr_helpdesk\main.py --server.port 8510
```

Then open:

```text
http://localhost:8510
```

## 8. Daily use commands

From the next day onward, the intern usually only needs:

```powershell
cd D:\AkhilaPrime_HR
docker start akhilaprime-hr-pgvector
.\.venv\Scripts\python.exe -m streamlit run hr_helpdesk\main.py
```

Rebuild the index only if:
- files in `docs/` changed
- the database was reset
- the embedding setup changed

Rebuild command:

```powershell
.\.venv\Scripts\python.exe hr_helpdesk\step2_indexing.py
```

## 9. Exact Python commands in this project

### Create virtual environment

```powershell
python -m venv .venv
```

### Upgrade pip

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

### Install requirements

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Run step 1 helper test

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from hr_helpdesk.step1_chunking import split_markdown_sections; text=Path('docs/POSH_Policy.md').read_text(encoding='utf-8'); chunks=split_markdown_sections(text); print(f'Chunks: {len(chunks)}'); [print(c.chunk_id, c.title) for c in chunks[:10]]"
```

### Run indexing

```powershell
.\.venv\Scripts\python.exe hr_helpdesk\step2_indexing.py
```

### Run indexing using module style

```powershell
.\.venv\Scripts\python.exe -m hr_helpdesk.step2_indexing
```

### Run retriever test

```powershell
.\.venv\Scripts\python.exe -c "from hr_helpdesk.step3_retriever import HRRetrievalPipeline, RetrievalConfig; result=HRRetrievalPipeline(RetrievalConfig()).retrieve('What is POSH policy?'); print('Strategy:', result.search_strategy); print('Docs:', len(result.docs)); [print(doc.metadata.get('title'), '|', doc.metadata.get('section_title')) for doc in result.docs]"
```

### Run Streamlit app from main entrypoint

```powershell
.\.venv\Scripts\python.exe -m streamlit run hr_helpdesk\main.py
```

### Run Streamlit app from direct app file

```powershell
.\.venv\Scripts\python.exe -m streamlit run hr_helpdesk\step4_app.py
```

### Run Streamlit on a custom port

```powershell
.\.venv\Scripts\python.exe -m streamlit run hr_helpdesk\main.py --server.port 8510
```

### Quick import and syntax check

```powershell
.\.venv\Scripts\python.exe -m compileall hr_helpdesk
```

## 10. Common problems

### Problem: `docker compose up -d` fails with container name conflict

That means the database container already exists.

Use:

```powershell
docker start akhilaprime-hr-pgvector
```

### Problem: `ModuleNotFoundError: No module named 'hr_helpdesk'`

Use the fixed entrypoint:

```powershell
.\.venv\Scripts\python.exe -m streamlit run hr_helpdesk\main.py
```

### Problem: blank white page in browser

Try:

1. Refresh with `Ctrl + F5`
2. Open in an incognito window
3. Run Streamlit on a different port

### Problem: Gemini API error

Check:

1. `GOOGLE_API_KEY` is correct in `.env`
2. Generative Language API is enabled
3. The key is allowed to use that API

### Problem: "Can I use someone else's Docker or environment?"

No.

The intern must use:

1. his own Docker Desktop
2. his own local container
3. his own `.venv`
4. his own `.env`
5. his own copy of the project folder

### Problem: app opens but answers do not work

Run indexing again:

```powershell
.\.venv\Scripts\python.exe hr_helpdesk\step2_indexing.py
```

## 11. Minimum command set for the intern

If the laptop is already set up, these are the 3 most important commands:

```powershell
cd D:\AkhilaPrime_HR
docker start akhilaprime-hr-pgvector
.\.venv\Scripts\python.exe -m streamlit run hr_helpdesk\main.py
```

If documents changed, add:

```powershell
.\.venv\Scripts\python.exe hr_helpdesk\step2_indexing.py
```
