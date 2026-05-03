# 🧠 Brain Vault AI

**Brain Vault AI** is a local AI-powered academic assistant designed to help students organize study material, understand subjects faster, and prepare smarter for exams.

It transforms scattered notes, PDFs, PYQs, and chapter lists into a structured learning vault powered by local AI models through Ollama.

---

# 🚀 Problem Statement(MY PERSONAL EXPERIENCE)

Students often struggle with:

- Notes scattered across folders, WhatsApp, PDFs, and notebooks
- Confusion about what to study first
- Weak topic identification
- Last-minute revision stress
- Difficulty converting notes into exam answers
- Wasting time searching instead of studying

---

# 💡 Solution

Brain Vault AI acts as a **personal study operating system**.

Students can upload materials, organize subjects, track weak chapters, ask AI questions, generate summaries, create exam answers, and receive revision plans — all in one place.

---

# ✨ Key Features

## 📚 Study Management
- Add subjects
- Add chapters / syllabus units
- Mark difficulty:
  - 🔴 Weak
  - 🟡 Average
  - 🟢 Strong

## 📂 Material Vault
Upload and organize:

- Notes
- Previous Year Questions (PYQ)
- Assignments
- Reference PDFs

Supports:

- PDF
- TXT
- DOCX

## 🤖 AI Study Assistant
Powered locally using Ollama.

- Ask subject questions
- Explain topics in simple language
- Smart summaries
- Important topic finder
- Weak topic coach

## 📝 Exam Intelligence

Generate:

- 2 Marker Answers
- 4 Marker Answers
- 8 Marker Answers
- Practice Questions
- Panic Mode (last-minute prep)
- Revision Plans

## 📊 Analytics

- Topic strength overview
- Subject engagement
- Weak area tracking
- Readiness score

---

# 🛠 Tech Stack

- Python
- Streamlit
- SQLite
- Ollama
- ChromaDB / FAISS
- PyPDF / python-docx

---

# 🧠 AI Models Used

Recommended:

- Chat Model: `gemma:2b`
- Embedding Model: `nomic-embed-text`

---

# 📁 Project Structure


brain_vault_ai/
│── app.py
│── modules/
│── uploads/
│── data/
│── requirements.txt
│── README.md
│── .gitignore
