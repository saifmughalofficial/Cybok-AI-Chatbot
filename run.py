"""Cybok launcher.

    python run.py                    start Cybok (http://127.0.0.1:5000)
    python run.py --port 8080        use another port
    python run.py --host 0.0.0.0     allow other devices on your network (phones, tablets)
    python run.py --dev              development mode with auto-reload
    python run.py make-admin EMAIL   give an existing account the admin role
    python run.py reset-password EMAIL
    python run.py set-creation-date YYYY-MM-DD   (or "" to clear)
    python run.py setup              connect a free AI model (Groq key / Ollama)
    python run.py check              test which AI models are reachable
"""
import argparse
import getpass
import os
import secrets
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


def ensure_env():
    """Create .env from the template on first run and make sure SECRET_KEY is a real random value."""
    example = ROOT / ".env.example"
    if not ENV_FILE.exists() and example.exists():
        ENV_FILE.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        print("  Created .env from .env.example")
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("SECRET_KEY="):
            if line.strip() in ("SECRET_KEY=", "SECRET_KEY=change-me"):
                lines[i] = "SECRET_KEY=" + secrets.token_urlsafe(48)
                ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
                print("  Generated a new SECRET_KEY in .env")
            break
    else:
        with ENV_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"\nSECRET_KEY={secrets.token_urlsafe(48)}\n")


def set_env_value(name, value):
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    for i, line in enumerate(lines):
        if line.startswith(f"{name}="):
            lines[i] = f"{name}={value}"
            break
    else:
        lines.append(f"{name}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_dependencies():
    missing = []
    for mod, pkg in (("flask", "Flask"), ("flask_sqlalchemy", "Flask-SQLAlchemy"), ("flask_login", "Flask-Login"),
                     ("authlib", "Authlib"), ("requests", "requests"), ("dotenv", "python-dotenv"),
                     ("pypdf", "pypdf"), ("docx", "python-docx"), ("openpyxl", "openpyxl"), ("PIL", "Pillow")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("\n  Missing packages: " + ", ".join(missing))
        print("  Install them with:\n\n      pip install -r requirements.txt\n")
        sys.exit(1)


def banner(url):
    line = "=" * 58
    print(f"\n  {line}\n   CYBOK  ·  Your AI. Your Workspace.\n  {line}")
    print(f"   Open in your browser:  {url}")
    print("   Stop the server:       press Ctrl + C in this window")
    print(f"  {line}\n")


def main():
    os.chdir(ROOT)
    check_dependencies()
    ensure_env()
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)

    parser = argparse.ArgumentParser(description="Run Cybok")
    parser.add_argument("command", nargs="?", default="serve",
                        choices=["serve", "setup", "make-admin", "reset-password", "set-creation-date", "check"])
    parser.add_argument("value", nargs="?")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "5000")))
    parser.add_argument("--dev", action="store_true", help="debug mode with auto-reload")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    args = parser.parse_args()

    from cybok import create_app
    from cybok.extensions import db
    app = create_app()

    if args.command == "make-admin":
        from cybok.models import User
        with app.app_context():
            u = User.query.filter_by(email=(args.value or "").lower()).first()
            if not u:
                sys.exit(f"  No account with e-mail {args.value!r}. Sign up first, then run this again.")
            u.role = "admin"
            db.session.commit()
            print(f"  {u.email} is now an admin. Open /admin after signing in.")
        return

    if args.command == "reset-password":
        from cybok.models import User
        from cybok.security import password_problem
        with app.app_context():
            u = User.query.filter_by(email=(args.value or "").lower()).first()
            if not u:
                sys.exit(f"  No account with e-mail {args.value!r}.")
            pw = getpass.getpass("  New password: ")
            problem = password_problem(pw)
            if problem:
                sys.exit("  " + problem)
            if pw != getpass.getpass("  Repeat password: "):
                sys.exit("  Passwords don't match.")
            u.set_password(pw)
            u.session_version += 1
            db.session.commit()
            print("  Password updated.")
        return

    if args.command == "set-creation-date":
        from datetime import date
        from cybok.appsettings import set_setting
        value = (args.value or "").strip()
        if value:
            date.fromisoformat(value)
        with app.app_context():
            set_setting("creation_date", value)
            db.session.commit()
        print(f"  Official creation date set to: {value or '(not configured)'}")
        return

    if args.command == "setup":
        print("\n  Cybok free AI setup\n  -------------------")
        print("  Option A (offline, no account): install Ollama from https://ollama.com and run:  ollama pull llama3.2")
        print("  Option B (fast cloud, free):    create a key at https://console.groq.com/keys\n")
        key = input("  Paste your free Groq key (or press Enter to skip): ").strip()
        if key:
            set_env_value("GROQ_API_KEY", key)
            print("  Saved GROQ_API_KEY to .env - Cybok Fast, Smart, GPT-OSS and Vision are now unlocked.")
        try:
            import requests
            requests.get("http://localhost:11434/api/tags", timeout=1)
            print("  Ollama is running - Cybok Local is available.")
        except Exception:
            print("  Ollama is not running (optional).")
        print("\n  Done. Start Cybok with:  start.bat   (or  python run.py)\n")
        return

    if args.command == "check":
        from cybok.ai.chat import ProviderError, complete, enabled_models, is_available
        with app.app_context():
            for m in enabled_models():
                if not is_available(m):
                    print(f"  [skip] {m.name:<26} needs {m.api_key_env}")
                    continue
                try:
                    reply = complete(m, [{"role": "user", "content": "Reply with: OK"}], max_tokens=300, timeout=40)
                    print(f"  [ OK ] {m.name:<26} {reply[:40]!r}")
                except ProviderError as exc:
                    print(f"  [FAIL] {m.name:<26} {str(exc)[:110]}")
        return

    shown_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{shown_host}:{args.port}"
    banner(url)
    if args.host in ("0.0.0.0", "::"):
        print("   Other devices on your Wi-Fi can use http://<this-computer's-IP>:%d\n" % args.port)
    if not args.no_browser and not os.environ.get("WERKZEUG_RUN_MAIN"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    if args.dev:
        app.run(host=args.host, port=args.port, debug=True, threaded=True)
        return
    try:
        from waitress import serve
        # send_bytes=1 flushes every chunk immediately so AI answers stream word by word.
        serve(app, host=args.host, port=args.port, threads=16, channel_timeout=300, send_bytes=1,
              ident="Cybok")
    except ImportError:
        app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
