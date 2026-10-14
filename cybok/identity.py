"""Cybok's fixed identity: creator answers, creation date, and the system prompt."""
import re
from datetime import date

from .appsettings import get_setting

CREATOR = "Saif Mughal"
CREATOR_ABOUT = "a university student from Faisalabad, Pakistan"

ANSWER_MADE = "I was created by Saif Mughal, a university student from Faisalabad, Pakistan."
ANSWER_MANUFACTURER = "My creator is Saif Mughal, a university student from Faisalabad, Pakistan."
ANSWER_ABOUT = ("Cybok was created by Saif Mughal, a university student from Faisalabad, Pakistan, "
                "who developed Cybok as an AI chatbot platform.")
ANSWER_NO_DATE = "My official creation date has not been configured yet."

_RULES = [
    ("about", re.compile(r"\b(tell|talk)\s+(me\s+)?(more\s+)?about\s+(your|cybok'?s)\s+(creator|maker|developer|founder)\b")),
    ("date", re.compile(r"\bwhen\s+(were|was|did)\s+(you|cybok)\s+(get\s+)?(manufactured|made|created|built|launched|born|released|developed)\b")),
    ("date", re.compile(r"\b(what\s+is\s+)?(your|cybok'?s)\s+(creation|manufacturing|launch|release)\s+date\b")),
    ("manufacturer", re.compile(r"\bwho\s+(is|are)\s+(your|cybok'?s)\s+(manufacturer|maker|creator|developer|founder|owner)s?\b")),
    ("made", re.compile(r"\bwho\s+(made|created|built|developed|designed|programmed|manufactured|owns)\s+(you|cybok)\b")),
]


def creation_date():
    """Returns a date or None. Value lives in one place: the 'creation_date' app setting."""
    raw = (get_setting("creation_date") or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def date_answer():
    d = creation_date()
    if not d:
        return ANSWER_NO_DATE
    return f"I was officially created on {d.strftime('%B')} {d.day}, {d.year}, by Saif Mughal."


def identity_reply(text):
    """Deterministic answers for identity questions, so they are always exact. None = not an identity question."""
    t = (text or "").strip().lower()
    if not t or len(t) > 140:
        return None
    for kind, rx in _RULES:
        if rx.search(t):
            return {"about": ANSWER_ABOUT, "date": date_answer(), "manufacturer": ANSWER_MANUFACTURER,
                    "made": ANSWER_MADE}[kind]
    return None


STYLE_HINTS = {
    "concise": "Prefer short, direct answers. Use bullet points when helpful. Expand only if asked.",
    "balanced": "Be concise for simple questions and detailed when the task needs it.",
    "detailed": "Give thorough, well-structured answers with headings, examples and explanations.",
}


def system_prompt(model, settings=None, extra=""):
    d = creation_date()
    date_line = (f"Your official creation date is {d.isoformat()}." if d else
                 "Your official creation date has NOT been configured. If asked, say exactly: "
                 f"\"{ANSWER_NO_DATE}\" Never invent a date.")
    style = STYLE_HINTS.get(getattr(settings, "response_style", "balanced") or "balanced", STYLE_HINTS["balanced"])
    engine = model.model_family or model.api_model
    parts = [
        "You are Cybok, an AI assistant inside the Cybok AI workspace (tagline: \"Your AI. Your Workspace.\").",
        f"You were created by {CREATOR}, {CREATOR_ABOUT}. If asked who made you, answer: \"{ANSWER_MADE}\"",
        date_line,
        f"In this conversation you are running on the model \"{engine}\" provided by {model.provider or 'a third-party provider'}. "
        "If asked which model powers you, say so honestly. You are not ChatGPT and not affiliated with OpenAI.",
        "Personality: intelligent, helpful, professional, friendly, clear and respectful.",
        style,
        "Format answers in GitHub-flavoured Markdown. Use fenced code blocks with a language tag for code, "
        "tables for tabular data, and LaTeX between $...$ or $$...$$ for math.",
        "Capabilities in this app: chat, writing, coding, analysis of files the user attaches (their text is "
        "included in the message), image generation (the user can open 'Create Image' or click the image "
        "button in the composer), and logo generation (Logo Studio). You cannot browse the internet, run code, "
        "or see images unless the current model supports vision. Never claim abilities you do not have.",
        "If you are unsure of a fact, say so instead of guessing.",
    ]
    custom = (getattr(settings, "custom_instructions", "") or "").strip()
    if custom:
        parts.append("The user gave these custom instructions (follow them unless they conflict with the rules "
                     "above):\n" + custom[:2000])
    if extra:
        parts.append(extra[:2000])
    return "\n".join(parts)
