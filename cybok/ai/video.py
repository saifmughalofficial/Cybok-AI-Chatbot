"""Text-to-video with Wan2.1 T2V 1.3B through Hugging Face Inference Providers (fal-ai)."""
from .images import ImageError, hf_error

VIDEO_MODEL = "Wan-AI/Wan2.1-T2V-1.3B"
VIDEO_LABEL = "Wan2.1 T2V 1.3B · Hugging Face"


def generate(prompt, token, seed=None, timeout=600):
    """Returns MP4 bytes. Thread-safe: no database access."""
    if not token:
        raise ImageError("Video generation needs a Hugging Face token: add HF_TOKEN in Admin › Free AI keys.")
    from huggingface_hub import InferenceClient
    client = InferenceClient(provider="auto", api_key=token, timeout=timeout)
    try:
        data = client.text_to_video(prompt.strip()[:1500], model=VIDEO_MODEL, seed=seed)
    except Exception as exc:
        raise ImageError(hf_error(exc, "Wan2.1 video"))
    if not data:
        raise ImageError("The video service returned an empty result. Please try again.")
    return data
