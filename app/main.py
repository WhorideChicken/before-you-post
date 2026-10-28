"""HTTP layer. Stateless by design: photos live only in memory for the length of one request."""
import functools
import hmac
import json
import logging
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import agent, meta, pipeline, samples

MAX_BYTES = 20 * 1024 * 1024
MAX_SIDE = 2048  # bounds time, cost and the size of the streamed result for a public demo
MAX_PHOTOS = 20  # an account scan; past 6 the photos are attacked one by one and linked (meta.MAX_TOGETHER)
LARGE_SIDE = 1536  # photos in an account that large are decoded smaller: 20 of them must fit the 512 MB host
UPLOAD_LIMIT = 6 * MAX_BYTES + 1024 * 1024  # the page shrinks photos before sending more than 6
MAX_CAPTION = 2200  # Instagram's caption limit
RUN_LEASE = 300  # seconds one live run may hold the only slot, in case its stream is never read
RUNS_PER_HOUR = int(os.environ.get("RUNS_PER_HOUR", "4"))  # per visitor, live model runs only
RUNS_PER_DAY = int(os.environ.get("RUNS_PER_DAY", "30"))  # whole site: about $3 of API calls at worst
# Without a key, live runs are off and only the recorded samples play. MOCK=1 runs the loop offline with a
# placeholder attacker instead, for local development. With only OPEN_API_KEY, live runs are private mode only.
STANDARD = meta.client is not None or os.environ.get("MOCK") == "1"
PRIVATE = meta.open_client is not None
LIVE = STANDARD or PRIVATE
# Judges' code: when set, live runs need it, so the public page cannot spend the credits. Samples stay open.
LIVE_CODE = os.environ.get("LIVE_CODE") or None
log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Before You Post")

_runs: dict[str, list[float]] = {}
_today: list[float] = []
_lock = threading.Lock()
_slot_free_at = [0.0]  # monotonic time the running live run releases the only slot at the latest


@app.middleware("http")
async def limit_upload(request: Request, call_next):
    """Refuse oversized uploads before the multipart body is parsed and spooled to disk."""
    if request.method == "POST":
        size = request.headers.get("content-length")
        if size is None or not size.isdigit() or int(size) > UPLOAD_LIMIT:
            return JSONResponse({"detail": "That upload is too large: up to 6 photos of 20 MB each, or more photos "
                                           "shrunk first (the page does that for you)."}, 413)
    return await call_next(request)


def allow_live_run(request: Request) -> None:
    """Rate limit for calls that spend API credits, and one live run at a time: a run holds up to a few hundred MB,
    and the demo host has 512. The last X-Forwarded-For hop is the one the host's proxy added; earlier entries are
    whatever the client sent."""
    if meta.client is None and meta.open_client is None:
        return
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[-1].strip() if forwarded else request.client.host
    now = time.time()
    # ponytail: in-memory, one container, reset on restart. The provider's spend limit is the real backstop.
    with _lock:
        for k in [k for k, v in _runs.items() if now - v[-1] >= 3600]:
            del _runs[k]
        _today[:] = [t for t in _today if now - t < 86400]
        recent = [t for t in _runs.get(ip, []) if now - t < 3600]
        if len(_today) >= RUNS_PER_DAY:
            raise HTTPException(429, "Today's live demo budget is used up. The sample photos still work.")
        if len(recent) >= RUNS_PER_HOUR:
            raise HTTPException(429, f"Live runs are limited to {RUNS_PER_HOUR} per hour. Try the sample photos.")
        if time.monotonic() < _slot_free_at[0]:
            raise HTTPException(429, "Someone else's photo is being checked. Try again in a minute, or play a sample.")
        _slot_free_at[0] = time.monotonic() + RUN_LEASE
        _runs[ip] = recent + [now]
        _today.append(now)


def release_run() -> None:
    _slot_free_at[0] = 0.0


async def read_image(photo: UploadFile, side: int = MAX_SIDE):
    data = await photo.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Photo is larger than 20 MB")
    try:
        return await run_in_threadpool(pipeline.load_image, data, side)
    except Exception:
        raise HTTPException(400, "Use a JPEG, PNG or WebP photo.")


def ndjson(lines) -> StreamingResponse:
    return StreamingResponse(lines, media_type="application/x-ndjson")


@app.get("/api/status")
def status():
    return {"live": LIVE, "standard": STANDARD, "private": PRIVATE, "mock": meta.client is None, "code": LIVE_CODE is not None}


@app.post("/api/run")
async def run(request: Request, photos: list[UploadFile] = File(...), private: bool = Form(False),
              code: str = Form(""), caption: str = Form(""), captions: str = Form("")):
    """Stream the agent's progress as NDJSON: attack, plan, edits, re-attack, done (with the final PNGs).
    Several photos are scanned as one account: attacked together, so combinations across them count.
    private: Muse Spark Open finds the clues and every edit runs here; nothing goes to Meta's API.
    caption: the text that will be posted with the photos; it is attacked with them and rewritten if it gives away
    what the edits hide. captions: a JSON list, one per photo, instead (an imported Instagram export)."""
    if not (PRIVATE if private else STANDARD):
        raise HTTPException(503, "This mode is switched off right now. The sample photos still work.")
    # ponytail: no lockout on wrong codes; use a long random code, since each guess is a full upload anyway.
    if LIVE_CODE and not hmac.compare_digest(code.encode(), LIVE_CODE.encode()):
        raise HTTPException(403, "That judges' code doesn't match. The sample photos work without one.")
    if len(photos) > MAX_PHOTOS:
        raise HTTPException(413, f"At most {MAX_PHOTOS} photos at once")
    try:
        texts = [caption] if not captions else json.loads(captions)
        assert isinstance(texts, list) and len(texts) <= len(photos) and all(isinstance(t, str) for t in texts)
    except (ValueError, AssertionError):
        raise HTTPException(400, "captions must be a JSON list of strings, one per photo")
    if any(len(t) > MAX_CAPTION for t in texts):
        raise HTTPException(413, f"Captions can be at most {MAX_CAPTION} characters, like Instagram's.")
    allow_live_run(request)
    try:
        side = MAX_SIDE if len(photos) <= meta.MAX_TOGETHER else LARGE_SIDE
        loaded = [await read_image(p, side) for p in photos]
    except BaseException:
        release_run()
        raise
    mock = not private and meta.client is None
    attack = meta.mock_attacker() if mock else functools.partial(meta.attack, private=private)
    read = None if mock else functools.partial(meta.read_text, private=private, effort=meta.ATTACK_EFFORT)
    rewrite = None if mock else functools.partial(meta.rewrite_caption, private=private)
    texts = [t.strip() for t in texts]

    def events():
        try:
            yield json.dumps({"type": "start", "metadata": [m for _, m in loaded], "mock": mock, "private": private,
                              "captions": texts}) + "\n"
            for event in agent.run([img for img, _ in loaded], attack=attack, private=private, read=read,
                                   caption=texts, rewrite=rewrite):
                yield json.dumps(event) + "\n"
        except Exception:
            log.exception("agent run failed")
            yield json.dumps({"type": "error", "text": "The check hit an error before it finished. Try again, or "
                                                       "play a sample."}) + "\n"
        finally:
            release_run()

    return ndjson(events())


@app.get("/api/sample/{name}")
def sample(name: str, speed: float = samples.SPEEDUP):
    """Replay a recorded run of one of the gallery photos, sped up (1-8x; the demo video paces it to the narration)."""
    if name not in samples.SOURCES:
        raise HTTPException(404, "No such sample")
    speed = min(max(speed, 1.0), 8.0)
    start = {"type": "start", "metadata": [], "mock": False, "replay": speed, "private": name in samples.PRIVATE,
             "captions": samples.captions(name)}
    return ndjson(samples.replay(name, json.dumps(start) + "\n", speed))


app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "static", html=True), name="static")
