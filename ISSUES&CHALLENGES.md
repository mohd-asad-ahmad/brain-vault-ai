# 🔥 Real Challenges I Faced — Brain Vault AI
### An honest account of what actually happened during development

> "This document is not a highlight reel. It's the real story — the bugs, the crashes,
> the late nights, and the lessons. Because that's what actual building looks like."

---

## 1. 🤖 The LLM Model Crisis — llama3 to gemma:2b

### What happened
I started the project planning to use **llama3** as my local LLM via Ollama. It was the most talked-about open model and seemed like the right choice. I built the entire AI chat pipeline around it — the RAG orchestration, the streaming logic, the system prompts — everything was wired for llama3.

### The problem
When I actually ran the app end to end, I kept getting:
```
ollama._types.ResponseError: model 'llama3' not found (status code: 404)
```
The model name was saved in my SQLite database from an early test session. Even when I selected `gemma:2b` in the UI dropdown, the app kept reading the old saved preference and sending requests to `llama3` — which wasn't installed.

### The debugging process
This was one of the most frustrating bugs because the error pointed to `ai_chat.py` and `ollama/_client.py` — not to the database setting. I spent significant time:
- Checking if Ollama was running ✅
- Checking if the model name was spelled correctly ✅
- Reinstalling the ollama Python library ✅
- Restarting Streamlit multiple times ✅

None of it helped. The actual fix was a single Python command to reset the saved model preference in the database:
```python
python -c "from modules.database import set_setting; set_setting('ollama_model', 'gemma:2b')"
```

### What I learned
Database-persisted settings can silently override UI selections. Always verify what value is actually being sent to the API, not just what the UI shows.

---

## 2. 🐛 The Ollama Library Version Break

### What happened
The `ollama` Python library released version **0.6.2** which completely changed how responses are returned. The old API returned plain Python dictionaries. The new API returns typed Pydantic objects.

### The broken code
```python
# This worked on older versions — broke silently on 0.6.2
chunk.get("message", {}).get("content")
resp.get("message") or {}
```

### The error
```
File "ollama/_client.py", line 189, in inner
    raise ResponseError(e.response.text, e.response.status_code)
```
The error pointed deep inside the Ollama library internals, not at my code — making it extremely hard to trace.

### The fix
```python
# New typed object access (v0.6.2+)
chunk.message.content
resp.message.content
```

### What I learned
Always check library changelogs when upgrading. A minor version bump (0.5.x → 0.6.x) can be a breaking change in Python libraries. Pin your versions in `requirements.txt`.

---

## 3. 💥 The Duplicate Code Bug in ai_chat.py

### What happened
During rapid development, a non-streaming `client.chat()` call was accidentally left **inside** the streaming `for chunk in stream` loop in `ask_brain_vault_stream()`. This meant on every single token received, the app was making a brand new blocking API call to Ollama — with an undefined variable `messages` on top of it.

### The broken code
```python
for chunk in stream:
    response = client.chat(      # ← full blocking call inside stream loop!
        model="gemma:2b",        # ← hardcoded, ignoring user selection
        messages=messages        # ← variable doesn't exist here!
    )
    yield response["message"]["content"]
```

### Why it was hard to catch
The error manifested as a `ResponseError` from Ollama — not a Python `NameError` or `TypeError`. So the traceback pointed to Ollama's internals, not the actual bad line. It took careful manual reading of the full function to spot the rogue nested call.

### What I learned
When copy-pasting or iterating quickly, always re-read the entire function — not just the lines you changed. Streaming functions need special care because bugs inside the loop multiply with every token.

---

## 4. 📦 The utils.py Module Issues

### What happened
`modules/utils.py` is the central config file — it holds `OLLAMA_HOST`, `OLLAMA_MODEL`, `SUGGESTED_CHAT_MODELS`, file type labels, difficulty labels, and other constants used across every other module. During development, inconsistencies crept in:

- Model names listed in `SUGGESTED_CHAT_MODELS` didn't match what was actually installed
- `OLLAMA_HOST` format caused connection issues on some runs
- Constants renamed in `utils.py` but not updated in modules that imported them — causing `ImportError` and `AttributeError` crashes across the app

### The cascading effect
Because every module imports from `utils.py`, a single wrong value there breaks the entire application — not just one feature. Errors would appear in completely unrelated pages like the uploader or analytics, making it seem like those modules were broken when the root cause was always in `utils.py`.

### What I learned
Central config files are high-risk. Any change there ripples everywhere. Treat `utils.py` like production infrastructure — change carefully and test immediately after every edit.

---

## 5. 🔄 State Sync Issues Across the App

### What happened
Streamlit reruns the entire script on every interaction. This caused a persistent issue: when I updated something in one part of the app (like indexing new files into the vector store), other parts of the app didn't immediately reflect that change.

**Example:** Upload a new PDF → Index it → Go to AI Study Assistant → Ask a question → The new file's content isn't in the answers yet because the vector store update hadn't fully propagated to the retrieval pipeline in the same session.

### Current status
This is a **known limitation** that still exists. The workaround is to manually trigger re-indexing from the "Build Knowledge Base" section before asking questions after new uploads. A proper fix would require background job queuing (Celery, APScheduler) which was out of scope for this project timeline.

---

## 6. 🌡️ Hardware — Overheating, Hanging, and Blue Screen

### What happened
Running all of this simultaneously on a standard laptop:
- **Ollama** with `gemma:2b` (1.7GB, 100% CPU)
- **ChromaDB** vector operations
- **Streamlit** web server
- **Screen recording** software

...pushed the system RAM and CPU to their absolute limits.

### The incidents
- The laptop became completely unresponsive mid-testing — mouse and keyboard frozen
- Had to force shutdown
- On restart: **Blue Screen of Death (BSOD)** — Windows reported a critical system error
- Lost unsaved progress and had to restart the entire development environment

### The cause
`gemma:2b` runs entirely on **CPU** (no GPU acceleration on this hardware). `ollama ps` confirmed: `100% CPU, 1.7GB RAM`. Combined with screen recording consuming another 1-2GB, the system simply ran out of resources.

### The workaround
- Close all unnecessary applications before running
- Never run screen recording simultaneously with Ollama inference
- Use phone to record screen instead of PC software
- Start Ollama first, let it load the model, then launch Streamlit

### Current limitation
Response times are **slow** — typically 1-3 minutes per query on CPU-only inference. This is a hardware limitation, not a software bug. On a machine with a dedicated GPU or with a cloud-hosted LLM, response times would be under 10 seconds.

---

## 7. ⚠️ Context Window Overflow — Silent Hanging

### What happened
The RAG pipeline retrieved large chunks of text and fed them directly to `gemma:2b`. The model has a **4096 token context limit**. When the combined context + question + system prompt exceeded this limit, the model didn't throw an error — it just silently hung, generating nothing, consuming 100% CPU indefinitely.

### How I found it
`ollama ps` showed the model running at 100% CPU with status `Stopping...` but no output ever appeared in the UI. After 10+ minutes of waiting with no response, it became clear the model was stuck.

### The fix
```python
# Truncate context before sending to model
if len(ctx) > 1500:
    ctx = ctx[:1500] + "\n...(truncated)"

# Limit tokens explicitly
options={"num_ctx": 2048, "num_predict": 512}
```

---

## 📊 Summary of Issues

| Challenge | Severity | Status |
|---|---|---|
| llama3 → gemma:2b model switch | 🔴 High | ✅ Fixed |
| Ollama library v0.6.2 breaking change | 🔴 High | ✅ Fixed |
| Duplicate code in streaming loop | 🔴 High | ✅ Fixed |
| utils.py cascading import errors | 🟡 Medium | ✅ Fixed |
| State sync across Streamlit reruns | 🟡 Medium | ⚠️ Known limitation |
| Context window overflow / silent hang | 🟡 Medium | ✅ Fixed |
| Hardware overheating / BSOD | 🔴 High | ⚠️ Hardware limitation |
| Slow inference speed on CPU | 🟡 Medium | ⚠️ Hardware limitation |

---

## 💬 Honest Reflection

This project taught me that **real software development is 20% building and 80% debugging**. Every error I hit made me understand the stack more deeply — from how Ollama manages model context, to how Streamlit's rerun model affects state, to how a single wrong line deep inside a streaming loop can bring down the entire feature.

I didn't have a smooth ride. But I shipped it. And every bug I fixed is now knowledge I own permanently.

---

*Mohd Asad Ahmad — ALTA AI Builders Fellowship*
