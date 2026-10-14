"""Chat model registry and a streaming client for any OpenAI-compatible API.

Groq, OpenRouter, Together, Mistral, DeepInfra, Ollama, LM Studio, vLLM and Pollinations all speak the
same /chat/completions protocol, so adding a new model is just a new row in the `ai_models` table
(Admin > Models) - no code change needed.
"""
import json
import os
import re
import time

import requests

from ..appsettings import get_setting
from ..extensions import db
from ..models import AIModel

# Every model below is free of charge:
#  - "Cybok Local" runs on your own computer with Ollama: no key, no internet, no limits.
#  - Groq / OpenRouter models need a free account key (no credit card). Paste it in Admin > System.
#  - "Cybok Open" is a keyless community service (best effort - it may be busy).
# If a model fails, Cybok automatically retries with the next available one.
DEFAULT_MODELS = [
    dict(slug="cybok-fast", name="Cybok Fast", badge="Fast · Vision", sort_order=10,
         description="Quick, multilingual answers. Can also look at images you attach.",
         provider="Groq", model_family="Qwen 3.8 27B (open-weight)",
         api_base="https://api.groq.com/openai/v1", api_model="qwen/qwen3.8-27b",
         api_key_env="GROQ_API_KEY", supports_vision=True, max_tokens=4096, context_chars=40000),
    dict(slug="cybok-smart", name="Cybok Smart", badge="Reasoning", sort_order=20,
         description="Thinks step by step - best for hard problems, maths, code and analysis.",
         provider="Groq", model_family="gpt-oss-120b (open-weight, Apache 2.0)",
         api_base="https://api.groq.com/openai/v1", api_model="openai/gpt-oss-120b",
         api_key_env="GROQ_API_KEY", max_tokens=8192, context_chars=60000, temperature=0.6),
    dict(slug="gpt-oss-20b", name="GPT-OSS 20B", badge="Quick reasoning", sort_order=30,
         description="Light reasoning model - shows its thinking, answers fast.",
         provider="Groq", model_family="gpt-oss-20b (open-weight, Apache 2.0)",
         api_base="https://api.groq.com/openai/v1", api_model="openai/gpt-oss-20b",
         api_key_env="GROQ_API_KEY", max_tokens=4096, context_chars=40000, temperature=0.6),
    dict(slug="openrouter-free", name="Open Model (OpenRouter)", badge="Free tier", sort_order=50,
         description="Free open-weight model via OpenRouter's free tier.",
         provider="OpenRouter", model_family="Meta Llama 3.3 70B Instruct (free)",
         api_base="https://openrouter.ai/api/v1", api_model="meta-llama/llama-3.3-70b-instruct:free",
         api_key_env="OPENROUTER_API_KEY", max_tokens=4096, context_chars=40000),
    dict(slug="ollama-local", name="Cybok Local", badge="No key · Offline", sort_order=15,
         description="Runs 100% on your own computer with Ollama. Free, private, works offline.",
         provider="Ollama (on this computer)", model_family="Meta Llama 3.2 3B (open-weight)",
         api_base="http://localhost:11434/v1", api_model="llama3.2",
         api_key_env="", key_required=False, max_tokens=2048, context_chars=16000),
    dict(slug="cybok-open", name="Cybok Open", badge="No key", sort_order=90,
         description="Keyless community service. Free but often busy - used as a last resort.",
         provider="Pollinations.ai (community)", model_family="gpt-oss-20b (open-weight, Apache 2.0)",
         api_base="https://text.pollinations.ai/openai", api_model="openai-fast",
         api_key_env="POLLINATIONS_TOKEN", key_required=False, supports_streaming=False, max_tokens=4096,
         context_chars=16000),
]

FREE_KEYS = {
    "GROQ_API_KEY": ("Groq", "https://console.groq.com/keys"),
    "OPENROUTER_API_KEY": ("OpenRouter", "https://openrouter.ai/keys"),
    "POLLINATIONS_TOKEN": ("Pollinations", "https://enter.pollinations.ai"),
    "HF_TOKEN": ("Hugging Face", "https://huggingface.co/settings/tokens"),
}


def get_secret(name):
    """A key from .env, or one pasted in Admin > System (stored server-side, never sent to browsers)."""
    if not name:
        return ""
    return (os.getenv(name) or get_setting(f"key:{name}") or "").strip()


class ProviderError(Exception):
    pass


# Provider models that were retired - rows still pointing at them are upgraded on start-up.
RETIRED_MODELS = {"llama-3.1-8b-instant", "llama-3.3-70b-versatile", "meta-llama/llama-4-scout-17b-16e-instruct"}
RETIRED_SLUGS = {"llama-4-scout": "meta-llama/llama-4-scout-17b-16e-instruct", "gpt-oss-120b": "openai/gpt-oss-120b",
                 "llama-instant": "llama-3.1-8b-instant"}


def seed_models():
    rows = {m.slug: m for m in AIModel.query.all()}
    for slug, model_id in RETIRED_SLUGS.items():  # duplicates/retired defaults (left alone if an admin edited them)
        if slug in rows and rows[slug].api_model == model_id:
            db.session.delete(rows.pop(slug))
    for spec in DEFAULT_MODELS:
        row = rows.get(spec["slug"])
        if row is None:
            db.session.add(AIModel(**spec))
        elif row.api_model in RETIRED_MODELS:
            for k, v in spec.items():
                setattr(row, k, v)
    db.session.commit()


def resolve_key(m):
    return (m.api_key or get_secret(m.api_key_env) or "").strip()


def is_local(m):
    return any(h in m.api_base for h in ("localhost", "127.0.0.1", "0.0.0.0"))


_local_cache = {}


def local_status(m):
    """For self-hosted servers (Ollama): is it running and is the model downloaded? Cached for 20 s."""
    base = m.api_base.rstrip("/")
    root = base[:-3] if base.endswith("/v1") else base
    hit = _local_cache.get(root)
    now = time.monotonic()
    if not hit or now - hit[0] > 20:
        try:
            r = requests.get(root + "/api/tags", timeout=0.8)
            names = {x.get("name", "") for x in r.json().get("models", [])} if r.ok else set()
            hit = (now, True, names)
        except (requests.RequestException, ValueError):
            hit = (now, False, set())
        _local_cache[root] = hit
    _, running, names = hit
    if not running:
        return "Install Ollama from ollama.com and keep it running"
    want = m.api_model if ":" in m.api_model else m.api_model + ":latest"
    if names and want not in names and m.api_model not in names:
        return f"Run: ollama pull {m.api_model}"
    return None


def unavailable_reason(m):
    if not m.enabled:
        return "Disabled by the administrator"
    if m.key_required and not resolve_key(m):
        name = FREE_KEYS.get(m.api_key_env, (m.provider, ""))[0]
        return f"Needs a free {name} key (Admin › System)"
    if is_local(m):
        return local_status(m)
    return None


def is_available(m):
    return unavailable_reason(m) is None


def model_public(m, default_slug=None):
    reason = unavailable_reason(m)
    return {
        "slug": m.slug, "name": m.name, "description": m.description, "provider": m.provider,
        "family": m.model_family, "badge": m.badge, "vision": m.supports_vision,
        "available": reason is None, "default": m.slug == default_slug, "needs": reason,
        "community": "community" in (m.provider or "").lower(),
    }


def enabled_models():
    return AIModel.query.filter_by(enabled=True).order_by(AIModel.sort_order, AIModel.id).all()


def default_model_slug():
    models = enabled_models()
    preferred = get_setting("default_model")
    for m in models:
        if m.slug == preferred and is_available(m):
            return m.slug
    for m in models:  # sort order already puts reliable free options first
        if is_available(m):
            return m.slug
    return models[0].slug if models else None


def fallback_models(primary, need_vision=False):
    """Other available models to try, in order, if `primary` fails before producing any text."""
    out = []
    for m in enabled_models():
        if m.id == primary.id or not is_available(m):
            continue
        if need_vision and not m.supports_vision:
            continue
        out.append(m)
    return out[:3]


def get_model(slug):
    m = AIModel.query.filter_by(slug=slug, enabled=True).first() if slug else None
    if m is None or not is_available(m):
        fallback = default_model_slug()
        m = AIModel.query.filter_by(slug=fallback).first() if fallback else None
    return m


def _endpoint(m):
    base = m.api_base.rstrip("/")
    if base.endswith("/chat/completions") or base.endswith("text.pollinations.ai/openai"):
        return base
    return base + "/chat/completions"


def _headers(m):
    h = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json"}
    key = resolve_key(m)
    if key:
        h["Authorization"] = f"Bearer {key}"
    if "openrouter.ai" in m.api_base:
        h["HTTP-Referer"] = os.getenv("PUBLIC_URL") or "http://localhost:5000"
        h["X-Title"] = "Cybok"
    return h


def _friendly(m, status, detail):
    detail = (detail or "").strip()[:300]
    if status in (401, 403):
        where = f" Set {m.api_key_env} in your .env file" if m.api_key_env else ""
        return f"{m.provider} rejected the API key.{where} and restart Cybok. ({detail})"
    if status == 404:
        return f"The model '{m.api_model}' was not found at {m.provider}. An admin can update it in Admin > Models. ({detail})"
    if status in (402, 503) and "community" in (m.provider or "").lower():
        return f"{m.provider} is busy or unavailable right now. Try another model."
    if status == 429:
        return f"{m.provider}'s free-tier rate limit was reached. Wait a moment or switch to another model."
    if status == 413 or "context" in detail.lower() and "length" in detail.lower():
        return "The conversation or attached file is too long for this model. Start a new chat or attach a smaller file."
    if status >= 500:
        return f"{m.provider} is having trouble right now ({status}). Please retry or pick another model."
    return f"{m.provider} returned an error ({status}): {detail}"


def _error_detail(resp):
    try:
        data = resp.json()
        err = data.get("error", data)
        if isinstance(err, dict):
            return err.get("message") or json.dumps(err)[:300]
        return str(err)
    except ValueError:
        return resp.text[:300]


def _post(m, payload, stream, timeout):
    try:
        resp = requests.post(_endpoint(m), json=payload, headers=_headers(m), stream=stream, timeout=(15, timeout))
    except requests.exceptions.ConnectionError:
        if "localhost" in m.api_base or "127.0.0.1" in m.api_base:
            raise ProviderError("Couldn't reach Ollama on this computer. Install it from ollama.com, then run "
                                f"'ollama pull {m.api_model}' and keep Ollama open.")
        raise ProviderError(f"Couldn't connect to {m.provider}. Check your internet connection.")
    except requests.exceptions.Timeout:
        raise ProviderError(f"{m.provider} took too long to respond. Please try again.")
    if resp.status_code != 200:
        detail = _error_detail(resp)
        resp.close()
        raise ProviderError(_friendly(m, resp.status_code, detail))
    return resp


def _extra_params(m):
    if "gpt-oss" in m.api_model and "groq.com" in m.api_base:
        return {"reasoning_effort": "low" if "20b" in m.api_model else "medium"}
    return {}


def stream_chat(m, messages, timeout=120):
    """Yields text chunks. Reasoning tokens (if the model emits them) are wrapped in <think> tags."""
    payload = {"model": m.api_model, "messages": messages, "temperature": m.temperature,
               "max_tokens": m.max_tokens, "stream": bool(m.supports_streaming)}
    payload.update(_extra_params(m))
    if "community" in (m.provider or "").lower():
        timeout = min(timeout, 40)  # best-effort service: fail fast so the fallback can take over
    resp = _post(m, payload, stream=True, timeout=timeout)
    try:
        ctype = resp.headers.get("Content-Type", "")
        if "text/event-stream" not in ctype:
            # Provider ignored stream=True: return the whole answer at once.
            resp.encoding = "utf-8"
            text = resp.text
            try:
                text = json.loads(text)["choices"][0]["message"].get("content") or ""
            except (ValueError, KeyError, IndexError, TypeError):
                pass
            # Re-stream the finished answer in small pieces so it still "types" smoothly in the UI.
            for piece in re.findall(r"\S+\s*|\s+", text):
                yield piece
                time.sleep(0.012)
            return
        resp.encoding = "utf-8"
        in_think = False
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            if obj.get("error"):
                raise ProviderError(f"{m.provider}: {obj['error'].get('message', obj['error']) if isinstance(obj['error'], dict) else obj['error']}")
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
            content = delta.get("content")
            if reasoning:
                if not in_think:
                    in_think = True
                    yield "<think>"
                yield reasoning
            if content:
                if in_think:
                    in_think = False
                    yield "</think>\n\n"
                yield content
        if in_think:
            yield "</think>\n\n"
    finally:
        resp.close()


def complete(m, messages, max_tokens=64, timeout=30):
    payload = {"model": m.api_model, "messages": messages, "temperature": 0.3, "max_tokens": max_tokens,
               "stream": False, **_extra_params(m)}
    resp = _post(m, payload, stream=False, timeout=timeout)
    try:
        resp.encoding = "utf-8"
        data = resp.json()
        return (data["choices"][0]["message"].get("content") or "").strip()
    except (ValueError, KeyError, IndexError, TypeError):
        raise ProviderError("Unexpected response from provider.")
    finally:
        resp.close()
