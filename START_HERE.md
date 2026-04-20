# AkhilaPrime HR Helpdesk: First-Time Setup Guide

This guide is for a beginner who already has the full project folder on their computer and wants to run the app from the start.

Everything below is written for Windows PowerShell.

## 1. What this project does

This project is a Streamlit HR helpdesk app.

It:
- reads HR policy files from the `docs/` folder
- stores searchable embeddings in PostgreSQL plus PGVector
- uses Google Gemini to answer HR questions
- opens a local web app using Streamlit

## 2. Things to install before running

Install these first on your laptop:

1. Python 3.10 or newer
2. VS Code or any editor
3. PowerShell terminal
4. Neon account (recommended for cloud storage) or Docker Desktop (optional for local storage)

## 3. Open the project folder

Open PowerShell and move into the project folder:

```powershell
cd D:\AkhilaPrime_HR
```

If your folder is in a different location, use that path instead.

## 4. Create the virtual environment

Run:

```powershell
python -m venv .venv
```

This creates a local Python environment inside the project.

## 5. Activate the virtual environment

Run:

```powershell
.\.venv\Scripts\Activate.ps1
```

After activation, your terminal usually shows `(.venv)` at the beginning.

If PowerShell blocks activation, run this once in the same terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate again:

```powershell
.\.venv\Scripts\Activate.ps1
```

## 6. Install Python packages

Use the requirements file:

```powershell
pip install -r requirements.txt
```

## 7. Create the `.env` file

Copy the sample environment file:

```powershell
Copy-Item .env.example .env
```

Now open `.env` and update at least this line:

```env
GOOGLE_API_KEY=your_google_api_key_here
```

Keep your real credentials only in `.env`.

## 8. Database Setup (Choose One)

### Option A: Neon Cloud (Recommended)
This project is pre-configured to use **Neon**. Since you are using Neon:
1. Ensure your `.env` has the `PGVECTOR_CONNECTION` pointing to your Neon database.
2. Ensure `sslmode=require` is in the connection string.
3. You can Skip the Docker steps below.

### Option B: Local Docker (Optional)
If you prefer running a database locally:
1. Start Docker Desktop.
2. Run `docker compose up -d`.

## 10. Build the vector index from the HR documents

Run:

```powershell
python -m hr_helpdesk.step2_indexing
```

This step:
- reads all files in `docs/`
- converts them into chunks
- creates embeddings
- stores them in PGVector

If this step succeeds, you should see a message showing how many chunks were indexed.

## 11. Run the Streamlit app

Run:

```powershell
streamlit run hr_helpdesk/step4_app.py
```

After that, Streamlit will show a local URL like:

```text
http://localhost:8501
```

Open that URL in your browser.

## 12. Every time you want to run the project again

From the project folder:

```powershell
cd D:\AkhilaPrime_HR
.\.venv\Scripts\Activate.ps1
# docker compose up -d  <-- Only if using local Docker
streamlit run hr_helpdesk/step4_app.py
```

You do not need to rebuild the index every time unless:
- documents inside `docs/` changed
- `.env` model settings changed
- database was reset

If documents changed, rebuild with:

```powershell
python -m hr_helpdesk.step2_indexing
```

## 13. Useful commands

Stop the app in the terminal:

```powershell
Ctrl + C
```

Stop Docker containers:

```powershell
docker compose down
```

See running Docker services:

```powershell
docker compose ps
```

## 14. Common problems

### Problem: `python` is not recognized

Fix:
- install Python
- while installing, enable Add Python to PATH

### Problem: virtual environment does not activate

Fix:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Problem: `docker compose up -d` fails

Fix:
- open Docker Desktop
- wait until Docker fully starts
- run the command again

### Problem: Gemini API error

Fix:
- check the `GOOGLE_API_KEY` inside `.env`
- make sure the Gemini / Generative Language API is enabled in your Google project

### Problem: app opens but answers fail

Fix:
1. Make sure Docker is running
2. Make sure `.env` has the correct Google API key
3. Rebuild the index:

```powershell
python -m hr_helpdesk.step2_indexing
```

## 15. Files you should know

- `docs/` -> HR policy documents
- `hr_helpdesk/step4_app.py` -> Streamlit app
- `hr_helpdesk/step2_indexing.py` -> builds the vector index
- `.env` -> your local secrets and settings
- `.env.example` -> sample configuration without real credentials
- `compose.yaml` -> Docker database setup
- `requirements.txt` -> Python package installation list

## 16. Full first-time command list

If you want the full flow in one place:

```powershell
cd D:\AkhilaPrime_HR
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Set up Neon or run: docker compose up -d
python -m hr_helpdesk.step2_indexing
streamlit run hr_helpdesk/step4_app.py
```

## 17. Beginner note

Run every command from the project root folder:

```text
D:\AkhilaPrime_HR
```

If you run commands from another folder, Python or Streamlit may not find the project files correctly.
