"""HTTP layer. Stateless by design: photos live only in memory for the length of one request."""
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from . import meta, pipeline

MAX_BYTES = 20 * 1024 * 1024
log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Before You Post")


class Edit(BaseModel):
    box: tuple[float, float, float, float] = Field(description="normalized x0, y0, x1, y1")
    action: Literal["erase", "pixelate", "blur"]
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


@app.post("/api/detect")
async def detect(photo: UploadFile = File(...)):
    img, metadata = await read_image(photo)
    try:
        findings = meta.detect(img)
    except Exception as e:
        raise HTTPException(502, f"Detection failed: {e}")
    return {"findings": findings, "metadata": metadata, "mock": meta.client is None}


@app.post("/api/apply")
async def apply(photo: UploadFile = File(...), edits: str = Form("[]")):
    try:
        edits = EDITS.validate_json(edits)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False))
    img, _ = await read_image(photo)
    pad = max(3, max(img.shape[:2]) // 200)
    engines = []
    for e in edits:
        box = tuple(min(max(v, 0.0), 1.0) for v in e.box)
        mask = meta.segment(img, e.label, box)
        mask = pipeline.grow(mask if mask is not None else pipeline.box_mask(img.shape, box), pad)
        if not mask.any():
            continue
        if e.action == "erase":
            try:
                edited, engine = meta.erase(img, e.label), "muse-image"
            except Exception:
                log.exception("Muse Image edit failed, falling back to inpaint")
                edited = None
            if edited is None:
                edited, engine = pipeline.inpaint(img, mask), "inpaint"
        else:
            edited, engine = getattr(pipeline, e.action)(img), e.action
        img = pipeline.composite(img, edited, mask)
        engines.append(engine)
    return Response(pipeline.encode_png(img), media_type="image/png", headers={"X-Engines": ",".join(engines)})


app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "static", html=True), name="static")
