# 🧠 Brain Vault AI – Development Prompt Log

This file documents the major prompts used during the AI-assisted development of **Brain Vault AI**.

It serves as a transparent build journal showing how the project was architected phase-by-phase using prompt-driven development with coding assistants.

---

# 📌 Project Overview

**Brain Vault AI** is a local AI-powered academic assistant built in Python.

Goal:

- Organize student study material
- Use local AI models via Ollama
- Help with summaries, exam prep, weak topics, and revision planning

---

# 🏗 Prompt Development Timeline

---

# 🔹 Initial Foundation Prompt

`
You are a senior Python software architect and production-grade developer.

Build PHASE 1 of a project called Brain Vault AI.

Goal:
Create a clean, scalable Python-only foundation for a local AI-powered student study assistant.

Tech Stack:
- Python
- Streamlit
- SQLite
- Modular architecture

Include:
1. Folder structure
2. requirements.txt
3. SQLite database
4. Dashboard UI
5. Subject management
6. Chapter management
7. Difficulty ratings
8. Sidebar navigation

Build PHASE 2 of Brain Vault AI.

Add study material upload and organization system.

Features:
- Upload PDF / TXT / DOCX
- Categorize:
  Notes
  PYQ
  Assignment
  Reference
- Save files into uploads/<subject>
- Extract text
- Store in SQLite
- Material library page
- Filters
- Analytics metrics

Rename all project references from Second Brain AI to Brain Vault AI.

Folder Name:
brain_vault_ai

Update:
- App title
- README
- Branding text
- Comments

Build PHASE 3 of Brain Vault AI.

Add local AI intelligence using Ollama.

Models:
- gemma:2b
- nomic-embed-text

Features:
- RAG chatbot with uploaded notes
- Summarizer
- Important topics finder
- Weak topic coach
- Chat history
- Build vector DB automatically

Build PHASE 4 of Brain Vault AI.

Add exam-focused tools.

Features:
- 2 marker answer generator
- 4 marker answer generator
- 8 marker answer generator
- PYQ practice mode
- Revision planner
- Panic mode
- Save exam history

Build PHASE 5 of Brain Vault AI.

Make app startup-grade.

Add:
- Study timeline
- Productivity tracking
- Reminders
- Readiness score
- Export center
- Analytics dashboard
- Settings page

Audit and fix Brain Vault AI runtime crashes.

Current installed Ollama models:

- gemma:2b
- nomic-embed-text

Tasks:
- Replace old model names like llama3 / phi3
- Fix streaming response crashes
- Use safe non-streaming ollama.chat()
- Fix embedding model config
- Add try/except
- Prevent hard crashes
- Create health_check.py
