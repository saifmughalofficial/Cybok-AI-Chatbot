"""Run models on free public Hugging Face Spaces (ZeroGPU) through gradio_client."""
import time


class SpaceError(Exception):
    pass


def client(space, token="", download=True):
    import httpx
    from gradio_client import Client
    try:
        return Client(space, token=token or None, verbose=False, download_files=download,
                      httpx_kwargs={"timeout": httpx.Timeout(60)})
    except Exception as exc:
        raise SpaceError(f"{space} is offline or starting up ({type(exc).__name__}).")


def friendly(exc):
    msg = str(exc)
    if "ZeroGPU" in msg or "quota" in msg.lower():
        return ("the free GPU quota is used up for now. Add a free Hugging Face token (HF_TOKEN) for more "
                "quota, or try again later.")
    return msg[:200] or type(exc).__name__


def run(job, timeout, progress=None, label="Working"):
    """Waits for a gradio job, reporting queue position / progress. Returns the outputs list."""
    start = time.time()
    while not job.done():
        if time.time() - start > timeout:
            job.cancel()
            raise SpaceError("timed out in the queue.")
        if progress:
            st = job.status()
            rank = getattr(st, "rank", None)
            pd = getattr(st, "progress_data", None) or []
            frac = None
            if pd and getattr(pd[0], "index", None) is not None and getattr(pd[0], "length", None):
                frac = pd[0].index / pd[0].length
            text = f"In queue — position {rank + 1}" if rank not in (None, 0) and str(st.code).endswith(
                "IN_QUEUE") else label
            progress(text, frac)
        time.sleep(1)
    try:
        job.result()
    except Exception as exc:
        raise SpaceError(friendly(exc))
    return job.outputs()
