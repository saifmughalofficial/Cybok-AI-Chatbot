"""Text-to-video with Wan2.1. Tries free Hugging Face Spaces first, then paid Inference Providers.

    1. multimodalart/self-forcing   Wan2.1-T2V-1.3B (Self-Forcing), free ZeroGPU, streams HLS -> remuxed to MP4
    2. HF Inference Providers       Wan-AI/Wan2.1-T2V-1.3B on fal-ai (uses HF credits)
"""
import os
import random
import subprocess
import tempfile
from urllib.parse import urljoin

import requests

from . import spaces
from .images import ImageError, hf_error

VIDEO_MODEL = "Wan-AI/Wan2.1-T2V-1.3B"
VIDEO_LABEL = "Wan2.1 T2V 1.3B"
SELF_FORCING = "multimodalart/self-forcing"


def _to_mp4(src_args, workdir):
    """Re-encodes to a browser-friendly MP4 with the ffmpeg binary bundled in imageio-ffmpeg."""
    import imageio_ffmpeg
    out = os.path.join(workdir, "out.mp4")
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", *src_args, "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", out],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not os.path.exists(out):
        raise ImageError(f"couldn't convert the video ({r.stderr[:120]}).")
    with open(out, "rb") as fh:
        return fh.read()


def _self_forcing(prompt, token, seed, timeout, progress):
    c = spaces.client(SELF_FORCING, token, download=False)
    job = c.submit(prompt, seed, 15, api_name="/video_generation_handler_streaming")
    spaces.run(job, timeout, progress, "Rendering frames")
    url = None
    for out in job.outputs():
        v = out[0] if isinstance(out, (list, tuple)) else out
        v = v.get("video", v) if isinstance(v, dict) else v
        v = v.get("url") or v.get("path") if isinstance(v, dict) else v
        if isinstance(v, str) and v.startswith(("http", "/")):
            url = urljoin(c.src.rstrip("/") + "/", v)
    if not url:
        raise ImageError("the Space returned no video.")
    if progress:
        progress("Downloading video", 0.95)
    return fetch_mp4(url, {"Authorization": f"Bearer {token}"} if token else {})


def fetch_mp4(url, headers=None):
    """Downloads an MP4 or an HLS playlist (+ segments) and returns browser-ready MP4 bytes."""
    headers = headers or {}
    with tempfile.TemporaryDirectory() as d:
        if url.split("?")[0].endswith(".m3u8"):
            playlist = requests.get(url, headers=headers, timeout=60).text
            segs = [urljoin(url, ln.strip()) for ln in playlist.splitlines() if ln.strip() and not ln.startswith("#")]
            if not segs:
                raise ImageError("the video stream was empty.")
            listing = os.path.join(d, "list.txt")
            with open(listing, "w") as fh:
                for i, s in enumerate(segs):
                    p = os.path.join(d, f"{i:04}.ts")
                    with open(p, "wb") as seg:
                        seg.write(requests.get(s, headers=headers, timeout=120).content)
                    fh.write(f"file '{p.replace(os.sep, '/')}'\n")
            return _to_mp4(["-f", "concat", "-safe", "0", "-i", listing], d)
        src = os.path.join(d, "in.mp4")
        with open(src, "wb") as fh:
            fh.write(requests.get(url, headers=headers, timeout=120).content)
        return _to_mp4(["-i", src], d)


def _providers(prompt, token, seed, timeout, progress):
    if not token:
        raise ImageError("needs HF_TOKEN.")
    from huggingface_hub import InferenceClient
    if progress:
        progress("Rendering on Hugging Face", None)
    try:
        data = InferenceClient(provider="auto", api_key=token, timeout=timeout).text_to_video(
            prompt, model=VIDEO_MODEL, seed=seed)
    except Exception as exc:
        raise ImageError(hf_error(exc, "Wan2.1"))
    if not data:
        raise ImageError("empty result.")
    return data


ENGINES = [
    ("Wan2.1 1.3B · Self-Forcing Space", _self_forcing),
    ("Wan2.1 1.3B · HF Inference Providers", _providers),
]


def generate(prompt, token="", seed=None, timeout=420, progress=None):
    """Returns (mp4_bytes, engine_label). Tries each engine until one works."""
    prompt = prompt.strip()[:1500]
    seed = seed if seed is not None else random.randint(1, 2_000_000_000)
    errors = []
    for label, fn in ENGINES:
        if progress:
            progress(f"Connecting to {label}", None)
        try:
            return fn(prompt, token, seed, timeout, progress), label
        except (ImageError, spaces.SpaceError) as exc:
            errors.append(f"{label}: {exc}")
        except Exception as exc:  # an engine changed its API: never crash, just try the next one
            errors.append(f"{label}: unexpected {type(exc).__name__}")
    hint = "" if token else (" — Tip: add a free Hugging Face token (HF_TOKEN in Admin › Free AI keys); free "
                             "accounts get daily GPU time for video.")
    raise ImageError("Video engines are busy right now. " + " | ".join(errors) + hint)
