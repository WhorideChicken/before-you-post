"""HTTP layer. Stateless by design: photos live only in memory for the length of one request."""
import itertools
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from . import agent, meta, pipeline, samples

MAX_BYTES = 20 * 1024 * 1024
MAX_SIDE = 2048  # bounds time, cost and the size of the streamed result for a public demo
RUNS_PER_HOUR = int(os.environ.get("RUNS_PER_HOUR", "4"))  # per visitor, live model runs only
RUNS_PER_DAY = int(os.environ.get("RUNS_PER_DAY", "30"))  # whole site: about $3 of API calls at worst
# Without a key, live runs are off and only the recorded samples play. MOCK=1 runs the loop offline with a
# placeholder attacker instead, for local development.
LIVE = meta.client is not None or os.environ.get("MOCK") == "1"
log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Before You Post")


class Edit(BaseModel):
    box: tuple[float, float, float, float] = Field(description="normalized x0, y0, x1, y1")
    action: Literal["erase", "replace", "pixelate", "blur"]
    label: str = Field("object", max_length=80)


EDITS = TypeAdapter(list[Edit])

_runs: dict[str, list[float]] = {}
_today: list[float] = []
_lock = threading.Lock()


def allow_live_run(request: Request) -> None:
    """Rate limit for calls that spend API credits. The last X-Forwarded-For hop is the one the host's proxy added;
    earlier entries are whatever the client sent."""
    if meta.client is None:
        return
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[-1].strip() if forwarded else request.client.host
    now = time.time()
    # ponytail: in-memory, one container. Move to a shared store if the demo ever runs more than one replica.
    with _lock:
        for k in [k for k, v in _runs.items() if now - v[-1] >= 3600]:
            del _runs[k]
        _today[:] = [t for t in _today if now - t < 86400]
        recent = _runs.get(ip, [])
        if len(_today) >= RUNS_PER_DAY:
            raise HTTPException(429, "Today's live demo budget is used up. The sample photos still work.")
        if len(recent) >= RUNS_PER_HOUR:
            raise HTTPException(429, f"Live runs are limited to {RUNS_PER_HOUR} per hour. Try the sample photos.")
        _runs[ip] = recent + [now]
        _today.append(now)


async def read_image(photo: UploadFile):
    data = await photo.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Photo is larger than 20 MB")
    try:
        return pipeline.load_image(data, MAX_SIDE)
    except Exception:
        raise HTTPException(400, "Not a readable image")


def ndjson(lines) -> StreamingResponse:
    return StreamingResponse(lines, media_type="application/x-ndjson")


@app.get("/api/status")
def status():
    return {"live": LIVE, "mock": meta.client is None}


def require_live() -> None:
    if not LIVE:
        raise HTTPException(503, "Live runs are switched off right now. The sample photos still work.")


@app.post("/api/run")
async def run(request: Request, photo: UploadFile = File(...)):
    """Stream the agent's progress as NDJSON: attack, plan, edits, re-attack, done (with the final PNG)."""
    require_live()
    img, metadata = await read_image(photo)
    allow_live_run(request)
    attack = meta.attack if meta.client else meta.mock_attacker()

    def events():
        yield json.dumps({"type": "start", "metadata": metadata, "mock": meta.client is None}) + "\n"
        try:
            for event in agent.run(img, attack=attack):
                yield json.dumps(event) + "\n"
        except Exception as e:
            log.exception("agent run failed")
            yield json.dumps({"type": "error", "text": f"{type(e).__name__}: {e}"}) + "\n"

    return ndjson(events())


@app.get("/api/sample/{name}")
def sample(name: str):
    """Replay a recorded run of one of the gallery photos, sped up."""
    if name not in samples.SOURCES:
        raise HTTPException(404, "No such sample")
    start = {"type": "start", "metadata": {"gps": False, "device": None}, "mock": False, "replay": samples.SPEEDUP}
    return ndjson(itertools.chain([json.dumps(start) + "\n"], samples.replay(name)))


@app.post("/api/apply")
async def apply(request: Request, photo: UploadFile = File(...), edits: str = Form("[]")):
    """Manual edits chosen by the user, same masking and compositing as the agent."""
    require_live()
    try:
        edits = EDITS.validate_json(edits)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False))
    img, _ = await read_image(photo)
    allow_live_run(request)
    items = [{"label": e.label, "action": e.action, "box": [min(max(v, 0.0), 1.0) for v in e.box]} for e in edits]
    img, done, _ = agent.apply_edits(img, items)
    return Response(pipeline.encode_png(img), media_type="image/png",
                    headers={"X-Engines": ",".join(d["engine"] for d in done)})


app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "static", html=True), name="static")
