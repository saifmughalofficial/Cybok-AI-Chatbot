# CYBOK — Your AI. Your Workspace.

A complete, **100% free** AI chatbot platform written in Python (Flask), with its own brand, UI and identity.

> Full step-by-step guide: **[docs/Cybok_User_Manual.pdf](docs/Cybok_User_Manual.pdf)**

## Quick start (Windows)

1. Install Python 3.10+ from python.org (tick **Add Python to PATH**).
2. Double-click **`start.bat`** — it installs everything and opens http://127.0.0.1:5000
3. Create your account (the first account becomes **admin**).
4. Connect a free AI engine (pick one or both):
   - **Ollama (offline, no key):** install from https://ollama.com then run `ollama pull llama3.2`
   - **Groq (free key, no card):** get a key at https://console.groq.com/keys and paste it in **Admin › System & APIs › Free AI keys**

Command line instead:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

macOS/Linux: `bash start.sh`

## Features

- Streaming AI chat with Markdown, code highlighting, tables, math (KaTeX), copy, regenerate, edit, stop, like/dislike, read-aloud
- Model selector with free open models (Groq, OpenRouter, Ollama, Pollinations) and **automatic fallback**
- Create Image (12 styles, 4 sizes, up to 4 images) and image generation inside chats
- Logo Studio: instant vector SVG logos + AI concepts
- File analysis: PDF, DOCX, PPTX, ODT, TXT, CSV, XLSX, JSON, HTML, code, images (vision models)
- Library with search, filters, sort, folders, preview, rename, download, delete
- Chat history: pin, rename, archive, trash & restore, export, global search (Ctrl+K), secure share links
- Voice: dictation, read-aloud, hands-free voice conversation
- Auth: e-mail/password, Google OAuth, password reset, change password, profile photo, delete account, data export
- Settings: account, appearance (light/dark/system, accent, text size), chat, voice, privacy, notifications, about
- Admin panel: stats & charts, users, AI models, free API keys, creation date, announcements, error log
- Security: CSRF, rate limiting, per-user data isolation, hashed passwords, server-side API keys, CSP & security headers, safe file handling

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
run.py                 launcher + CLI
cybok/__init__.py      app factory
cybok/models.py        database models (users, conversations, messages, files, generated content, settings…)
cybok/ai/chat.py       model registry + streaming OpenAI-compatible client + fallback
cybok/ai/images.py     image providers (Pollinations, Hugging Face)
cybok/ai/logos.py      vector logo generator
cybok/files.py         secure uploads + text extraction
cybok/identity.py      Cybok's identity answers + system prompt
cybok/routes/          auth, pages, JSON API, admin API
cybok/templates/       HTML pages
cybok/static/          CSS, JavaScript, logo
instance/              database + uploaded files (created on first run — back this up)
```

Add a new model without code: **Admin › AI Models › Add model** (any OpenAI-compatible API).

---

Cybok · Manufactured by Saif Mughal — University Student • Faisalabad, Pakistan
