# Second Brain AI — Phase 1

Local, Python-only foundation for a student study assistant: subjects, chapters, difficulty tracking, and analytics. **No AI features yet** — structured for future Ollama / RAG integration.

## Requirements

- Python 3.11+

## Setup

```bash
cd brain_vault_ai
python -m venv .venv
```

Activate the virtual environment (Windows PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

Prefer the module form so it works even when `Scripts` is not on your `PATH` (common on Windows):

```bash
python -m streamlit run app.py
```

Alternatively: `streamlit run app.py` after activating a venv or ensuring Streamlit’s install directory is on `PATH`.

The SQLite database file is created automatically at `data/second_brain.db` on first run. Default sample subjects (DBMS, OS, Python, AI) are inserted when the subjects table is empty.

## Project layout

- `app.py` — Streamlit entry and pages
- `modules/database.py` — SQLite schema and initialization
- `modules/subjects.py` — Subject/chapter operations and analytics queries
- `modules/ui.py` — Sidebar and shared UI helpers
- `modules/utils.py` — Constants and paths
- `data/` — Database directory (gitignored DB optional; use `.gitkeep` for empty folder)

## Difficulty ratings

| Value   | Meaning        |
|---------|----------------|
| `red`   | Weak           |
| `yellow`| Average        |
| `green` | Easy / strong  |

## License

Use and modify for your own study workflow.
