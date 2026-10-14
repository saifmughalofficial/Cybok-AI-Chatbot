"""Builds docs/Cybok_User_Manual.pdf.   Run:  python docs/build_manual.py"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "Cybok_User_Manual.pdf"
LOGO = ROOT / "cybok" / "static" / "img" / "logo.jpg"
MARK = ROOT / "cybok" / "static" / "img" / "mark.png"

INK = colors.HexColor("#0d1020")
MUTED = colors.HexColor("#5b6178")
BLUE = colors.HexColor("#2f6bff")
RED = colors.HexColor("#e5384a")
SOFT = colors.HexColor("#f1f3f9")
LINE = colors.HexColor("#dfe3ee")
DARK = colors.HexColor("#07080d")

ss = getSampleStyleSheet()
S = {
    "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=25, textColor=INK, spaceBefore=4, spaceAfter=10, keepWithNext=1),
    "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13.5, leading=18, textColor=BLUE, spaceBefore=12, spaceAfter=6, keepWithNext=1),
    "body": ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=10.3, leading=15, textColor=INK, spaceAfter=6),
    "small": ParagraphStyle("small", parent=ss["BodyText"], fontName="Helvetica", fontSize=9, leading=12.5, textColor=MUTED),
    "bullet": ParagraphStyle("bullet", parent=ss["BodyText"], fontName="Helvetica", fontSize=10.3, leading=15, leftIndent=14, bulletIndent=3, textColor=INK, spaceAfter=2),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=9.4, leading=12.6, textColor=colors.HexColor("#e6e8f2"), leftIndent=0),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=9.4, leading=12.5, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=9.4, leading=12.5, textColor=INK),
    "tip": ParagraphStyle("tip", fontName="Helvetica", fontSize=9.8, leading=14, textColor=INK),
}


def P(text, style="body"):
    return Paragraph(text, S[style])


def bullets(items):
    return [Paragraph(t, S["bullet"], bulletText="\u2022") for t in items]


def code(text):
    t = Table([[Preformatted(text.strip("\n"), S["code"])]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#11142a")),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                           ("ROUNDEDCORNERS", [6, 6, 6, 6])]))
    return KeepTogether([t, Spacer(1, 7)])


def tip(text, kind="tip"):
    color = {"tip": BLUE, "warn": RED}[kind]
    label = {"tip": "TIP", "warn": "IMPORTANT"}[kind]
    t = Table([[P(f'<font color="{color.hexval()}"><b>{label}</b></font>&nbsp;&nbsp;{text}', "tip")]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 7),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return KeepTogether([t, Spacer(1, 8)])


def table(rows, widths, header=True):
    data = [[P(c, "cellb" if (header and i == 0) else "cell") for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), SOFT))
    t.setStyle(TableStyle(style))
    return KeepTogether([t, Spacer(1, 8)])


def on_page(canvas, doc):
    canvas.saveState()
    if doc.page > 1:
        canvas.drawImage(str(MARK), 20 * mm, 284 * mm, 6 * mm, 6 * mm, mask="auto")
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.setFillColor(INK)
        canvas.drawString(28 * mm, 285.6 * mm, "CYBOK")
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(43 * mm, 285.6 * mm, "User Manual")
        canvas.drawRightString(190 * mm, 285.6 * mm, "Your AI. Your Workspace.")
        canvas.setStrokeColor(LINE)
        canvas.line(20 * mm, 282 * mm, 190 * mm, 282 * mm)
        canvas.drawCentredString(105 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(DARK)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFillColor(colors.Color(1, 0.2, 0.28, alpha=0.18))
    canvas.circle(10 * mm, 30 * mm, 90 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.Color(0.18, 0.45, 1, alpha=0.18))
    canvas.circle(200 * mm, 270 * mm, 90 * mm, fill=1, stroke=0)
    canvas.setFillAlpha(1)
    canvas.drawImage(str(LOGO), 52.5 * mm, 128 * mm, 105 * mm, 105 * mm)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 30)
    canvas.drawCentredString(105 * mm, 108 * mm, "User Manual")
    canvas.setFont("Helvetica", 14)
    canvas.setFillColor(colors.HexColor("#b5bad3"))
    canvas.drawCentredString(105 * mm, 98 * mm, "Install, run and use Cybok - step by step, without help")
    canvas.setFont("Helvetica-Bold", 13)
    canvas.setFillColor(colors.HexColor("#7fa8ff"))
    canvas.drawCentredString(105 * mm, 84 * mm, "Your AI. Your Workspace.")
    canvas.setFont("Helvetica", 10)
    canvas.setFillColor(colors.HexColor("#8f95b2"))
    canvas.drawCentredString(105 * mm, 30 * mm, "Version 1.0  |  100% free AI chatbot platform")
    canvas.drawCentredString(105 * mm, 23 * mm, "Manufactured by Saif Mughal  -  University Student, Faisalabad, Pakistan")
    canvas.restoreState()


def build():
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=24 * mm,
                            bottomMargin=20 * mm, title="Cybok User Manual", author="Saif Mughal", subject="Cybok - Your AI. Your Workspace.")
    st = [PageBreak()]

    # ---------------------------------------------------------------- contents
    st += [P("Contents", "h1")]
    toc = ["1. What is Cybok?", "2. What you need", "3. Quick start (5 minutes)", "4. Running Cybok from the command line",
           "5. Connect a free AI model (Ollama or Groq)", "6. Your first sign-in", "7. Using Cybok",
           "8. Keyboard shortcuts", "9. Admin panel", "10. Command reference", "11. Optional extras (Google sign-in, e-mail, phones, going online)",
           "12. Troubleshooting", "13. Your data, backups and updates", "14. About Cybok"]
    st += [P(t) for t in toc]
    st.append(PageBreak())

    # ---------------------------------------------------------------- 1
    st += [P("1. What is Cybok?", "h1"),
           P("Cybok is a complete, <b>free</b> AI workspace that runs on your own computer and opens in your web browser. "
             "It looks and feels like a modern AI assistant, with its own identity, design and features:"),
           *bullets(["<b>AI Chat</b> - ask questions, write, translate, summarize, code, debug, solve math and brainstorm. Answers appear word by word.",
                     "<b>Create Image</b> - turn a text description into pictures in 12 styles.",
                     "<b>Logo Studio</b> - instant vector logos plus AI-designed logo concepts for any brand.",
                     "<b>File analysis</b> - upload PDF, Word, Excel, CSV, PowerPoint, text, code or images and ask about them.",
                     "<b>Library</b> - every upload, image, logo and saved answer in one searchable place.",
                     "<b>Chat history</b> - auto-saved chats with pin, rename, archive, delete, restore, search and share.",
                     "<b>Voice</b> - talk to Cybok and hear answers out loud.",
                     "<b>Admin panel</b> - users, statistics, AI models, free API keys, announcements and Cybok's official creation date."]),
           tip("Cybok uses only free, openly licensed AI models (Meta Llama, gpt-oss, FLUX). You never pay anything. "
               "The model in use is always shown under the message box.")]

    # ---------------------------------------------------------------- 2
    st += [P("2. What you need", "h1"),
           table([["Item", "Details"],
                  ["Computer", "Windows 10/11 (also works on macOS and Linux). 8 GB RAM or more recommended for the offline model."],
                  ["Python", "Version 3.10 or newer from <b>python.org/downloads</b>. During installation tick <b>\"Add Python to PATH\"</b>."],
                  ["Internet", "Needed the first time (to install packages). Afterwards Cybok can run fully offline with Ollama."],
                  ["Disk space", "About 300 MB for Cybok, plus about 2 GB for the free offline AI model (optional)."],
                  ["Browser", "Chrome or Edge recommended (needed for voice input). Firefox and Safari work for everything else."]], [32, 138]),
           tip("To check Python, open a terminal and type <font face='Courier'>python --version</font>. You should see "
               "<font face='Courier'>Python 3.10</font> or higher.")]

    # ---------------------------------------------------------------- 3
    st += [P("3. Quick start (5 minutes)", "h1"),
           P("The easiest way - no typing needed:"),
           *bullets(["<b>Step 1.</b> Install Python (see section 2).",
                     "<b>Step 2.</b> Open the folder <b>Project 4 [Cybok] AI Chatbot</b>.",
                     "<b>Step 3.</b> Double-click <b>start.bat</b>. The first start installs everything automatically (1-3 minutes).",
                     "<b>Step 4.</b> Your browser opens <b>http://127.0.0.1:5000</b>. Click <b>Start Chatting</b> and create your account.",
                     "<b>Step 5.</b> Connect a free AI model (section 5) - then start chatting!"]),
           tip("Keep the black start.bat window open while you use Cybok - it is the Cybok server. Close it (or press Ctrl + C) to stop Cybok.", "warn"),
           tip("The <b>first account</b> you create automatically becomes the <b>administrator</b>.")]

    # ---------------------------------------------------------------- 4
    st += [PageBreak(), P("4. Running Cybok from the command line", "h1"),
           P("If you prefer typing commands, or you are on macOS/Linux, follow these steps exactly."),
           P("Windows (PowerShell or Command Prompt)", "h2"),
           P("1) Open the project folder in a terminal. In File Explorer, open the Cybok folder, click the address bar, type <b>powershell</b> and press Enter. Or:"),
           code('cd "C:\\Users\\<YourName>\\OneDrive\\Desktop\\Project 4 [Cybok] AI Chatbot"'),
           P("2) Create a private Python environment (first time only):"),
           code("python -m venv .venv"),
           P("3) Install Cybok's packages (first time only, and after updates):"),
           code(".venv\\Scripts\\python.exe -m pip install -r requirements.txt"),
           P("4) Start Cybok:"),
           code(".venv\\Scripts\\python.exe run.py"),
           P("5) Open <b>http://127.0.0.1:5000</b> in your browser (it usually opens by itself)."),
           tip("Shortcut: in Command Prompt you can simply run <font face='Courier'>start.bat</font> - it does steps 2-4 for you every time."),
           P("macOS / Linux (Terminal)", "h2"),
           code('cd ~/path/to/"Project 4 [Cybok] AI Chatbot"\nbash start.sh\n\n# or manually:\npython3 -m venv .venv\n.venv/bin/python -m pip install -r requirements.txt\n.venv/bin/python run.py'),
           P("Useful start options", "h2"),
           table([["Command", "What it does"],
                  ["<font face='Courier'>python run.py</font>", "Start Cybok on http://127.0.0.1:5000"],
                  ["<font face='Courier'>python run.py --port 8080</font>", "Use a different port if 5000 is busy"],
                  ["<font face='Courier'>python run.py --host 0.0.0.0</font>", "Let phones/tablets on your Wi-Fi open Cybok"],
                  ["<font face='Courier'>python run.py --no-browser</font>", "Don't open the browser automatically"],
                  ["<font face='Courier'>python run.py --dev</font>", "Developer mode with auto-reload"]], [70, 100]),
           P("On Windows, write <font face='Courier'>.venv\\Scripts\\python.exe</font> instead of <font face='Courier'>python</font> in these commands "
             "(or activate the environment first with <font face='Courier'>.venv\\Scripts\\activate</font>).", "small")]

    # ---------------------------------------------------------------- 5
    st += [PageBreak(), P("5. Connect a free AI model", "h1"),
           P("Cybok is free, but it needs at least one AI engine. Choose <b>one or both</b> options - both cost nothing. "
             "If one engine is busy, Cybok automatically answers with the next available one."),
           table([["", "Option A: Ollama (offline)", "Option B: Groq (cloud)"],
                  ["Cost", "Free forever", "Free tier, no credit card"],
                  ["Account", "None", "Free Groq account"],
                  ["Internet", "Not needed after download", "Needed"],
                  ["Speed", "Depends on your PC (CPU)", "Very fast"],
                  ["Models in Cybok", "Cybok Local", "Cybok Fast, Cybok Smart, GPT-OSS 120B, Llama 4 Vision"]], [34, 68, 68]),
           P("Option A - Ollama: AI on your own computer", "h2"),
           *bullets(["Download and install Ollama from <b>https://ollama.com/download</b> (or run the command below).",
                     "Download the free model once (about 2 GB):"]),
           code("winget install Ollama.Ollama      # Windows - or use the installer from ollama.com\nollama pull llama3.2"),
           P("Ollama runs in the background (look for the llama icon near the clock). Refresh Cybok and pick <b>Cybok Local</b> in the model menu."),
           P("Option B - free Groq key", "h2"),
           *bullets(["Open <b>https://console.groq.com/keys</b> and sign up (Google sign-in works).",
                     "Click <b>Create API Key</b> and copy the key (it starts with <font face='Courier'>gsk_</font>).",
                     "In Cybok open <b>your profile menu > Admin panel > System &amp; APIs > Free AI keys</b>, paste the key next to Groq and click <b>Save</b>.",
                     "Refresh the page - Cybok Fast, Cybok Smart, GPT-OSS 120B and Llama 4 Vision are now unlocked."]),
           P("Prefer the command line? This asks for the key and saves it into the <b>.env</b> file:"),
           code(".venv\\Scripts\\python.exe run.py setup"),
           P("To test every model at once:"),
           code(".venv\\Scripts\\python.exe run.py check"),
           tip("Keep keys secret. Cybok stores them only on the server and never sends them to the browser.", "warn"),
           P("Other free options: an <b>OpenRouter</b> key (openrouter.ai/keys) unlocks the OpenRouter free model; a <b>Hugging Face</b> "
             "token lets you switch the image generator to FLUX.1-schnell on Hugging Face. Images work without any key by default.", "small")]

    # ---------------------------------------------------------------- 6
    st += [P("6. Your first sign-in", "h1"),
           *bullets(["Open Cybok and click <b>Start Chatting</b>, then <b>Create an account</b> (name, e-mail, password with a letter and a number).",
                     "The first account becomes the <b>admin</b>. Later accounts are normal users.",
                     "<b>Forgot your password?</b> Click <i>Forgot password?</i> on the sign-in page. If e-mail isn't configured, the reset link is "
                     "printed in the black server window - copy it into your browser.",
                     "Admins can also reset a password from the command line: <font face='Courier'>python run.py reset-password you@example.com</font>"])]

    # ---------------------------------------------------------------- 7
    st += [PageBreak(), P("7. Using Cybok", "h1"),
           P("Chatting", "h2"),
           *bullets(["Type in the message box and press <b>Enter</b> to send (<b>Shift + Enter</b> for a new line).",
                     "Answers stream in live. Press the <b>stop</b> button (or <b>Esc</b>) to stop early.",
                     "Under each answer: <b>Copy</b>, <b>Read aloud</b>, <b>Regenerate</b>, <b>Like/Dislike</b>, <b>Save to Library</b> and <b>Share</b>.",
                     "Hover your own message and click the pencil to <b>edit</b> it - Cybok answers again from that point.",
                     "Code appears in highlighted blocks with a <b>Copy</b> button. Tables, lists, headings and math formulas are formatted automatically.",
                     "Reasoning models show a collapsible <b>Reasoning</b> section with their thinking."]),
           P("Choosing a model", "h2"),
           P("Click the model name at the top of the chat. Every model shows its real name and provider. Greyed-out models tell you exactly what "
             "free step unlocks them. Set your favourite in <b>Settings > Chat > Default model</b>."),
           P("Files and documents", "h2"),
           *bullets(["Click the <b>paperclip</b>, drag files onto the message box, or paste a screenshot (Ctrl + V).",
                     "Supported: PDF, DOCX, PPTX, ODT, TXT, MD, CSV, TSV, XLSX, JSON, HTML, code files and images (PNG, JPG, WebP, GIF, BMP). Default limit: 20 MB.",
                     "Then ask: <i>\"Summarize this PDF\"</i>, <i>\"Find the important numbers in this Excel file\"</i>, <i>\"Explain this document\"</i>.",
                     "Spreadsheets get automatic statistics (sum, average, min, max) so number questions are accurate.",
                     "To ask about pictures, choose a model marked <b>Vision</b> (Llama 4 Scout Vision)."]),
           P("Create Image", "h2"),
           *bullets(["Open <b>Create Image</b> in the sidebar, describe your picture, pick a style, size and number of images, then click <b>Generate</b>.",
                     "Hover a result to <b>save to Library</b>, <b>download</b>, <b>regenerate</b>, reuse the prompt or <b>delete</b>. Click to view full size.",
                     "Inside a chat, click the <b>image</b> button next to the paperclip to create an image right in the conversation."]),
           P("Logo Studio", "h2"),
           P("Enter brand name, industry, style, colors (names or #hex codes), symbol and typography. You instantly get 6 vector (SVG) concepts "
             "plus optional AI-designed concepts. Save favourites to your Library and download them."),
           P("Library", "h2"),
           P("All your uploads, saved images, logos and saved answers. Search, filter by type, sort, switch grid/list view, preview, rename, "
             "move into folders, download, delete, or click <b>Ask Cybok about this</b> to start a chat with a file."),
           P("History, pinning, archive and trash", "h2"),
           *bullets(["Chats save automatically and are grouped by date in the sidebar.",
                     "Click <b>...</b> on a chat to <b>Rename</b> (or double-click / F2), <b>Pin</b>, <b>Share</b>, <b>Export</b>, <b>Archive</b> or <b>Delete</b>.",
                     "Pinned chats stay at the top. Deleted chats go to <b>Archived &amp; Trash</b> for 30 days and can be restored.",
                     "Turn off <b>Settings > Privacy > Save chat history</b> for temporary chats that are removed when you sign out."]),
           P("Search", "h2"),
           P("Press <b>Ctrl + K</b> (or click Search) to search chat titles and message text, files (including text inside documents), images, logos and saved answers, and to run quick commands."),
           P("Sharing", "h2"),
           P("Click the <b>share</b> icon, then <b>Create link</b>. Anyone with the link sees a read-only copy - never your name, e-mail or other chats. "
             "Disable or replace the link at any time (Settings > Privacy > Shared links)."),
           P("Voice", "h2"),
           *bullets(["<b>Microphone</b> button: dictate your message (speech to text).",
                     "<b>Speaker</b> button under an answer: read it aloud. Turn on auto-read in <b>Settings > Voice</b> and choose a voice and speed.",
                     "<b>Headphones</b> button: hands-free voice conversation - speak, Cybok answers out loud, then listens again.",
                     "The browser asks for microphone permission the first time. Voice input works in Chrome and Edge."]),
           P("Settings", "h2"),
           P("Open from your profile menu (bottom-left) or press <b>Ctrl + ,</b>. Sections: <b>Account</b> (name, e-mail, photo, password, sign out everywhere, "
             "delete account), <b>Appearance</b> (light/dark/system, accent color, text size), <b>Chat</b> (default model, response style, Enter-to-send, custom "
             "instructions), <b>Voice</b>, <b>Privacy &amp; Data</b> (history, export, shared links, delete all chats), <b>Notifications</b>, <b>Shortcuts</b> and <b>About</b>.")]

    # ---------------------------------------------------------------- 8
    st += [P("8. Keyboard shortcuts", "h1"),
           table([["Action", "Keys"], ["Search everything", "Ctrl + K"], ["New chat", "Ctrl + Shift + O"], ["Show / hide sidebar", "Ctrl + B"],
                  ["Image mode in chat", "Ctrl + Shift + I"], ["Focus the message box", "Shift + Esc"], ["Stop generating", "Esc"],
                  ["Copy last answer", "Ctrl + Shift + C"], ["New line", "Shift + Enter"], ["Rename selected chat", "F2"],
                  ["Settings", "Ctrl + ,"], ["Show all shortcuts", "Ctrl + /"]], [100, 70])]

    # ---------------------------------------------------------------- 9
    st += [PageBreak(), P("9. Admin panel", "h1"),
           P("Admins see <b>Admin panel</b> in the profile menu (or open <b>http://127.0.0.1:5000/admin</b>). Normal users cannot open it."),
           table([["Tab", "What you can do"],
                  ["Overview", "Total and active users, conversations, AI requests, image generations, uploads, storage, 14-day activity chart, model usage."],
                  ["Users", "Search users, enable/disable accounts, make someone admin, delete users."],
                  ["AI Models", "Add, edit, enable/disable or delete models, change order, test a model. Any OpenAI-compatible API works."],
                  ["System &amp; APIs", "Paste <b>free AI keys</b>, set Cybok's <b>official creation date</b>, open/close sign-ups, max upload size, default model, extra system prompt, image provider."],
                  ["Announcements", "Show a banner message to all users (info, success or warning)."],
                  ["System errors", "See provider failures and server errors; clear the log."]], [36, 134]),
           P("Cybok's official creation date", "h2"),
           P("When someone asks <i>\"When were you manufactured?\"</i>, Cybok answers with the date set in <b>Admin > System &amp; APIs > Cybok identity</b>. "
             "If no date is set, Cybok honestly says: <i>\"My official creation date has not been configured yet.\"</i> It never invents a date. "
             "From the command line:"),
           code('.venv\\Scripts\\python.exe run.py set-creation-date 2026-10-08\n.venv\\Scripts\\python.exe run.py set-creation-date ""      # clear it'),
           P("Adding another free model", "h2"),
           P("Admin > AI Models > <b>Add model</b>. Fill in: display name, slug, provider label, model family, API base URL "
             "(e.g. <font face='Courier'>https://api.groq.com/openai/v1</font> or <font face='Courier'>http://localhost:11434/v1</font>), the provider's model id, "
             "and the key's environment variable name. Click <b>Test</b> to verify. No code changes or restart needed.")]

    # ---------------------------------------------------------------- 10
    st += [P("10. Command reference", "h1"),
           P("Run these inside the Cybok folder. On Windows use <font face='Courier'>.venv\\Scripts\\python.exe</font> in place of <font face='Courier'>python</font>.", "small"),
           table([["Command", "Purpose"],
                  ["<font face='Courier'>start.bat</font>", "One-click install + start (Windows)"],
                  ["<font face='Courier'>bash start.sh</font>", "One-click install + start (macOS / Linux)"],
                  ["<font face='Courier'>python run.py</font>", "Start the Cybok server"],
                  ["<font face='Courier'>python run.py setup</font>", "Save a free Groq key and check Ollama"],
                  ["<font face='Courier'>python run.py check</font>", "Test which AI models answer"],
                  ["<font face='Courier'>python run.py make-admin EMAIL</font>", "Give an account the admin role"],
                  ["<font face='Courier'>python run.py reset-password EMAIL</font>", "Set a new password for an account"],
                  ["<font face='Courier'>python run.py set-creation-date YYYY-MM-DD</font>", "Set Cybok's official creation date"],
                  ["<font face='Courier'>ollama pull llama3.2</font>", "Download the free offline model"],
                  ["<font face='Courier'>python docs/build_manual.py</font>", "Rebuild this PDF manual"]], [85, 85])]

    # ---------------------------------------------------------------- 11
    st += [PageBreak(), P("11. Optional extras", "h1"),
           P("All settings live in the <b>.env</b> file in the Cybok folder (open it with Notepad). Restart Cybok after editing it.", "body"),
           P("Use Cybok on your phone (same Wi-Fi)", "h2"),
           code(".venv\\Scripts\\python.exe run.py --host 0.0.0.0"),
           P("Find your PC's IP address with <font face='Courier'>ipconfig</font> (e.g. 192.168.1.20) and open <b>http://192.168.1.20:5000</b> on your phone. "
             "Allow Python through Windows Firewall when asked. Add it to your home screen to use it like an app."),
           P("Continue with Google", "h2"),
           *bullets(["Go to <b>console.cloud.google.com/apis/credentials</b>, create an <b>OAuth client ID</b> of type <b>Web application</b>.",
                     "Add the redirect URI <font face='Courier'>http://127.0.0.1:5000/auth/google/callback</font> (and your real domain later).",
                     "Put the values in .env: <font face='Courier'>GOOGLE_CLIENT_ID=...</font> and <font face='Courier'>GOOGLE_CLIENT_SECRET=...</font>, then restart."]),
           P("Password-reset e-mails", "h2"),
           P("Fill <font face='Courier'>MAIL_SERVER</font>, <font face='Courier'>MAIL_PORT</font>, <font face='Courier'>MAIL_USERNAME</font>, "
             "<font face='Courier'>MAIL_PASSWORD</font> in .env. For Gmail use smtp.gmail.com, port 587 and an <b>App Password</b>."),
           P("Putting Cybok online", "h2"),
           *bullets(["Use a server or a host that runs Python (for example a VPS, Render or Railway). Run <font face='Courier'>python run.py --host 0.0.0.0 --no-browser</font>.",
                     "Put HTTPS in front (Nginx, Caddy or Cloudflare) and set <font face='Courier'>PUBLIC_URL=https://your-domain</font>, "
                     "<font face='Courier'>SESSION_COOKIE_SECURE=true</font> and <font face='Courier'>BEHIND_PROXY=true</font>.",
                     "Online, use Groq for AI (Ollama only works where it is installed). For many users, PostgreSQL can be used via <font face='Courier'>DATABASE_URL</font>."])]

    # ---------------------------------------------------------------- 12
    st += [P("12. Troubleshooting", "h1"),
           table([["Problem", "Solution"],
                  ["'python' is not recognized", "Reinstall Python and tick <b>Add Python to PATH</b>, or use <font face='Courier'>py</font> instead of <font face='Courier'>python</font>."],
                  ["Port 5000 already in use", "Start with <font face='Courier'>run.py --port 8080</font> and open http://127.0.0.1:8080"],
                  ["\"Connect a free AI model\" banner", "No AI engine is connected yet. Follow section 5 (Ollama or a free Groq key)."],
                  ["Cybok Local is greyed out", "Install Ollama, run <font face='Courier'>ollama pull llama3.2</font>, make sure Ollama is running, then refresh."],
                  ["Groq models are greyed out", "Paste your key in Admin > System &amp; APIs > Free AI keys, or run <font face='Courier'>run.py setup</font>."],
                  ["\"rate limit reached\"", "Free tiers limit requests per minute. Wait a moment or pick another model."],
                  ["Slow answers with Cybok Local", "Normal on older CPUs. Close heavy apps, or use Groq for speed."],
                  ["Image generation fails", "The free image service may be busy - retry in a few seconds. Check your internet connection."],
                  ["No text found in a PDF", "Scanned PDFs are pictures. Use a text PDF, or take a screenshot and ask a Vision model."],
                  ["Microphone doesn't work", "Use Chrome or Edge and allow microphone access (padlock icon in the address bar)."],
                  ["Forgot admin password", "<font face='Courier'>run.py reset-password your@email.com</font>"],
                  ["Page looks broken / old", "Press Ctrl + F5 to reload without cache."]], [55, 115])]

    # ---------------------------------------------------------------- 13
    st += [P("13. Your data, backups and updates", "h1"),
           *bullets(["All data is stored in the <b>instance</b> folder: <font face='Courier'>instance\\cybok.db</font> (database) and "
                     "<font face='Courier'>instance\\storage</font> (files and images).",
                     "<b>Backup:</b> stop Cybok and copy the whole <b>instance</b> folder and your <b>.env</b> file somewhere safe.",
                     "<b>Restore:</b> put them back in the Cybok folder and start Cybok.",
                     "<b>Each user</b> can export their own data in Settings > Privacy &amp; Data > Export.",
                     "<b>Updating:</b> replace the program files but keep <b>instance</b> and <b>.env</b>, then run start.bat (it installs any new packages)."]),
           tip("Never share your .env file or the instance folder - they contain secret keys and private conversations.", "warn")]

    # ---------------------------------------------------------------- 14
    st += [P("14. About Cybok", "h1"),
           P("<b>Cybok</b> - Your AI. Your Workspace."),
           P("Created by <b>Saif Mughal</b>, University Student, Faisalabad, Pakistan."),
           P("Ask Cybok <i>\"Who made you?\"</i> and it answers: <i>\"I was created by Saif Mughal, a university student from Faisalabad, Pakistan.\"</i>"),
           P("Cybok is an independent platform. It is not ChatGPT and is not affiliated with OpenAI or any model provider. "
             "AI models are third-party open models, identified by name and provider inside the app."),
           Spacer(1, 30),
           Image(str(MARK), 22 * mm, 22 * mm),
           Spacer(1, 6),
           Paragraph("Manufactured by Saif Mughal", ParagraphStyle("c", parent=S["small"], alignment=TA_CENTER))]

    doc.build(st, onFirstPage=cover, onLaterPages=on_page)
    print(f"Manual written to {OUT}")


if __name__ == "__main__":
    build()
