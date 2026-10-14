# CYBOK — Your AI. Your Workspace.

A complete, **100% free** AI chatbot platform written **entirely in Python**, with a **Streamlit** UI, its own brand and identity.

> Full step-by-step guide: **[docs/Cybok_User_Manual.pdf](docs/Cybok_User_Manual.pdf)**

## Quick start (Windows)

1. Install Python 3.10+ from python.org (tick **Add Python to PATH**).
2. Double-click **`start.bat`** — it installs everything and opens http://127.0.0.1:5000
3. Create your account (the first account becomes **admin**).
4. Connect a free AI engine (pick one or both):
   - **Ollama (offline, no key):** install from https://ollama.com then run `ollama pull llama3.2`
   - **Groq (free key, no card):** get a key at https://console.groq.com/keys and paste it in **Admin › Free AI keys**

Command line instead:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py            # or: streamlit run app.py
```

macOS/Linux: `bash start.sh`

## Features

- Streaming AI chat with Markdown, code, tables, math, copy, regenerate, edit & resend, stop, like/dislike
- Model selector with free open models (Groq, OpenRouter, Ollama, Pollinations) and **automatic fallback**
- Voice dictation in the chat box (Groq Whisper, needs the free Groq key)
- Create Image (12 styles, 4 sizes, up to 4 images) and `/image <prompt>` inside chats
- Logo Studio: instant vector SVG logos + AI concepts
- File analysis: PDF, DOCX, PPTX, ODT, TXT, CSV, XLSX, JSON, HTML, code, images (vision models)
- Library with search, filters, sort, folders, preview, rename, download, delete
- Chat history: pin, rename, archive, trash & restore, export, global search, share links (`?share=…`)
- Auth: e-mail/password, "keep me signed in", password reset, change password, profile photo, delete account, data export
- Settings: account, response style, custom instructions, default model, chat text size, privacy
- Admin panel: stats & charts, users, AI models, free API keys, creation date, announcements, error log
- Security: rate limiting, per-user data isolation, hashed passwords, server-side API keys, safe file handling

## Commands

| Command | Purpose |
|---|---|
| `python run.py` | Start Cybok (`--port`, `--host 0.0.0.0`, `--dev`, `--no-browser`) |
| `python run.py setup` | Save a free Groq key / check Ollama |
| `python run.py check` | Test all AI models |
| `python run.py make-admin EMAIL` | Make a user admin |
| `python run.py reset-password EMAIL` | Reset a password |
| `python run.py set-creation-date YYYY-MM-DD` | Cybok's official creation date |
| `python docs/build_manual.py` | Rebuild the PDF manual |

## Project layout

```
app.py                 Streamlit UI (all pages: chat, images, logos, library, search, settings, admin)
run.py                 launcher + CLI
cybok/__init__.py      database setup (Flask-SQLAlchemy container, no web server)
cybok/services.py      business logic used by the UI (auth, chats, streaming, files, admin…)
cybok/models.py        database models (users, conversations, messages, files, generated content, settings…)
cybok/ai/chat.py       model registry + streaming OpenAI-compatible client + fallback
cybok/ai/images.py     image providers (Pollinations, Hugging Face)
cybok/ai/logos.py      vector logo generator
cybok/files.py         secure uploads + text extraction
cybok/identity.py      Cybok's identity answers + system prompt
.streamlit/config.toml theme
instance/              database + uploaded files (created on first run — back this up)
```

Add a new model without code: **Admin › AI models › Add model** (any OpenAI-compatible API).

---

Cybok · Manufactured by Saif Mughal — University Student • Faisalabad, Pakistan
