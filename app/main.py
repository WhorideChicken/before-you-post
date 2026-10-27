"""HTTP layer. Stateless by design: photos live only in memory for the length of one request."""
import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from . import agent, meta, pipeline

MAX_BYTES = 20 * 1024 * 1024
log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Before You Post")


class Edit(BaseModel):
    box: tuple[float, float, float, float] = Field(description="normalized x0, y0, x1, y1")
    action: Literal["erase", "replace", "pixelate", "blur"]
    label: str = Field("object", max_length=80)


EDITS = TypeAdapter(list[Edit])


async def read_image(photo: UploadFile):
    data = await photo.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Photo is larger than 20 MB")
    try:
        return pipeline.load_image(data)
    except Exception:
        raise HTTPException(400, "Not a readable image")


@app.post("/api/run")
async def run(photo: UploadFile = File(...)):
    """Stream the agent's progress as NDJSON: attack, plan, edits, re-attack, done (with the final PNG)."""
    img, metadata = await read_image(photo)
    attack = meta.attack if meta.client else meta.mock_attacker()

    def events():
        yield json.dumps({"type": "start", "metadata": metadata, "mock": meta.client is None}) + "\n"
        try:
            for event in agent.run(img, attack=attack):
                yield json.dumps(event) + "\n"
        except Exception as e:
            log.exception("agent run failed")
            yield json.dumps({"type": "error", "text": f"{type(e).__name__}: {e}"}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.post("/api/apply")
async def apply(photo: UploadFile = File(...), edits: str = Form("[]")):
    """Manual edits chosen by the user, same masking and compositing as the agent."""
    try:
        edits = EDITS.validate_json(edits)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False))
    img, _ = await read_image(photo)
    items = [{"label": e.label, "action": e.action, "box": [min(max(v, 0.0), 1.0) for v in e.box]} for e in edits]
    img, done = agent.apply_edits(img, items)
    return Response(pipeline.encode_png(img), media_type="image/png",
                    headers={"X-Engines": ",".join(d["engine"] for d in done)})


app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "static", html=True), name="static")
