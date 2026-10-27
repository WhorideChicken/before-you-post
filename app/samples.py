"""Recorded agent runs for the sample gallery: real results that play instantly and cost no API calls.

Record (needs MODEL_API_KEY): uv run --env-file .env python -m app.samples
"""
import base64
import json
import shutil
import time
from pathlib import Path

SAMPLES = Path(__file__).parent.parent / "static" / "samples"
BENCH = Path(__file__).parent.parent / "bench" / "images"
SOURCES = {"desk": "desk_parcel", "front_door": "front_door", "kr_parcel": "kr_parcel", "inj_poster": "inj_poster"}
SPEEDUP = 4


def replay(name: str):
    """Yield the recorded NDJSON lines, paced like the real run but SPEEDUP times faster."""
    prev = 0.0
    for line in (SAMPLES / f"{name}.ndjson").read_text(encoding="utf-8").splitlines():
        t = json.loads(line)["t"]
        time.sleep(min(max(t - prev, 0.0) / SPEEDUP, 5.0))
        prev = t
        yield line + "\n"


def record(name: str) -> None:
    from . import agent, pipeline

    src = SAMPLES / f"{name}.jpg"
    if not src.exists():
        shutil.copy(BENCH / f"{SOURCES[name]}.jpg", src)
    img, _ = pipeline.load_image(src.read_bytes())
    t0, lines = time.time(), []
    for event in agent.run(img):
        event = {**event, "t": round(time.time() - t0, 1)}
        if event["type"] == "done":
            (SAMPLES / f"{name}.safe.png").write_bytes(base64.b64decode(event.pop("image")))
            event["image_url"] = f"samples/{name}.safe.png"
        lines.append(json.dumps(event, ensure_ascii=False))
    (SAMPLES / f"{name}.ndjson").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"recorded {name}: {lines[-1][:160]}", flush=True)


if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor

    from . import meta

    assert meta.client, "recording needs MODEL_API_KEY (run with --env-file .env)"
    with ThreadPoolExecutor(len(SOURCES)) as pool:
        list(pool.map(record, SOURCES))
