"""Image generation providers. Add a provider by writing one function and registering it in PROVIDERS."""
import os
import random
import time
from urllib.parse import quote

import requests

from ..appsettings import get_setting

STYLES = {
    "none": ("No style", ""),
    "photo": ("Photorealistic", "photorealistic, ultra detailed, natural lighting, 35mm photography, sharp focus"),
    "cinematic": ("Cinematic", "cinematic still, dramatic lighting, film grain, anamorphic, color graded"),
    "digital": ("Digital art", "digital art, highly detailed, vibrant colors, trending illustration"),
    "anime": ("Anime", "anime style, studio quality, clean line art, cel shading"),
    "3d": ("3D render", "3d render, octane render, soft global illumination, high detail"),
    "cyberpunk": ("Cyberpunk", "cyberpunk, neon lights, red and blue glow, futuristic, rain, night"),
    "watercolor": ("Watercolor", "watercolor painting, soft washes, paper texture"),
    "oil": ("Oil painting", "oil painting, visible brush strokes, classical composition"),
    "minimal": ("Minimal flat", "minimal flat vector illustration, clean shapes, limited palette"),
    "pixel": ("Pixel art", "pixel art, 16-bit, crisp pixels"),
    "sketch": ("Pencil sketch", "pencil sketch, graphite, hand drawn, cross hatching"),
}

SIZES = {
    "square": (1024, 1024),
    "portrait": (832, 1216),
    "landscape": (1216, 832),
    "wide": (1344, 768),
}


class ImageError(Exception):
    pass


def build_prompt(prompt, style):
    suffix = STYLES.get(style, STYLES["none"])[1]
    return f"{prompt.strip()}, {suffix}" if suffix else prompt.strip()


def _pollinations(prompt, width, height, seed, timeout, cfg):
    model = cfg.get("image_model") or "flux"
    url = f"https://image.pollinations.ai/prompt/{quote(prompt[:1500], safe='')}"
    params = {"width": width, "height": height, "seed": seed, "model": model, "nologo": "true",
              "private": "true", "safe": "true"}
    headers = {}
    token = cfg.get("pollinations_token", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, params=params, headers=headers, timeout=(15, timeout))
        if r.status_code == 429:  # one request at a time on the free tier: wait briefly and retry once
            time.sleep(4)
            r = requests.get(url, params=params, headers=headers, timeout=(15, timeout))
        if r.status_code == 402 and max(width, height) > 512:
            # The keyless free tier limits image size: retry at a smaller size with the same aspect ratio.
            scale = 512 / max(width, height)
            params.update(width=int(width * scale) // 8 * 8, height=int(height * scale) // 8 * 8)
            r = requests.get(url, params=params, headers=headers, timeout=(15, timeout))
    except requests.exceptions.Timeout:
        raise ImageError("The image service took too long. Please try again.")
    except requests.exceptions.ConnectionError:
        raise ImageError("Couldn't reach the image service. Check your internet connection.")
    ctype = r.headers.get("Content-Type", "")
    if r.status_code != 200 or not ctype.startswith("image/"):
        if r.status_code == 429:
            raise ImageError("The free image service is busy (rate limit). Wait a few seconds and retry.")
        if r.status_code == 402:
            raise ImageError("The free image service's no-key limit was reached. Try again later, or add a free "
                             "Pollinations token in Admin › System for higher limits.")
        raise ImageError(f"Image service error ({r.status_code}). Please try again.")
    return r.content, ctype.split(";")[0], f"Pollinations.ai · {model}"


def _huggingface(prompt, width, height, seed, timeout, cfg):
    token = cfg.get("hf_token", "")
    if not token:
        raise ImageError("Hugging Face is selected as image provider but HF_TOKEN is not set in .env.")
    model = cfg.get("hf_image_model") or "black-forest-labs/FLUX.1-schnell"
    url = f"https://router.huggingface.co/hf-inference/models/{model}"
    payload = {"inputs": prompt[:1500], "parameters": {"width": width, "height": height, "seed": seed}}
    try:
        r = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}", "Accept": "image/png"},
                          timeout=(15, timeout))
    except requests.exceptions.RequestException:
        raise ImageError("Couldn't reach Hugging Face. Check your internet connection.")
    ctype = r.headers.get("Content-Type", "")
    if r.status_code != 200 or not ctype.startswith("image/"):
        try:
            detail = r.json().get("error", "")
        except ValueError:
            detail = r.text[:200]
        raise ImageError(f"Hugging Face error ({r.status_code}): {detail}")
    return r.content, ctype.split(";")[0], f"Hugging Face · {model.split('/')[-1]}"


PROVIDERS = {
    "pollinations": ("Pollinations.ai (free, no key)", _pollinations),
    "huggingface": ("Hugging Face Inference (HF_TOKEN)", _huggingface),
}


def image_config():
    """Read provider settings from the database (call inside a request, before starting worker threads)."""
    from .chat import get_secret
    cfg = {k: get_setting(k) for k in ("image_provider", "image_model", "hf_image_model")}
    cfg["hf_token"] = get_secret("HF_TOKEN")
    cfg["pollinations_token"] = get_secret("POLLINATIONS_TOKEN")
    return cfg


def generate(prompt, cfg, style="none", size="square", seed=None, timeout=150):
    """Returns (image_bytes, mime, provider_label, seed). Thread-safe: no database access."""
    width, height = SIZES.get(size, SIZES["square"])
    seed = seed if seed is not None else random.randint(1, 2_000_000_000)
    _, fn = PROVIDERS.get(cfg.get("image_provider") or "pollinations", PROVIDERS["pollinations"])
    data, mime, label = fn(build_prompt(prompt, style), width, height, seed, timeout, cfg)
    return data, mime, label, seed
