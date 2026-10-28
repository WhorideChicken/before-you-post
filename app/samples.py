"""Recorded agent runs for the sample gallery: real results that play instantly and cost no API calls.

Record (needs MODEL_API_KEY): uv run --env-file .env python -m app.samples [name ...]
"""
import base64
import json
import shutil
import time
from pathlib import Path

SAMPLES = Path(__file__).parent.parent / "static" / "samples"
BENCH = Path(__file__).parent.parent / "bench" / "images"
# sample name -> LeakBench photos, served as static/samples/{name}-{1..n}.jpg. Several photos = one account scan.
SOURCES = {"desk": ["desk_parcel"], "front_door": ["front_door"], "kr_parcel": ["kr_parcel"],
           "inj_poster": ["inj_poster"], "account": ["acct_cup", "acct_class", "acct_town"],
           "desk_private": ["desk_parcel"]}
PRIVATE = {"desk_private"}  # recorded in private mode: Muse Spark Open, edits on the server
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
    from . import agent, meta, pipeline

    imgs = []
    for i, source in enumerate(SOURCES[name], 1):
        src = SAMPLES / f"{name}-{i}.jpg"
        if not src.exists():
            shutil.copy(BENCH / f"{source}.jpg", src)
        imgs.append(pipeline.load_image(src.read_bytes())[0])
    t0, lines = time.time(), []
    private = name in PRIVATE
    for event in agent.run(imgs, attack=lambda ims: meta.attack(ims, private=private), private=private):
        event = {**event, "t": round(time.time() - t0, 1)}
        if event["type"] == "done":
            event["image_urls"] = []
            for i, png in enumerate(event.pop("images"), 1):
                (SAMPLES / f"{name}-{i}.safe.png").write_bytes(base64.b64decode(png))
                event["image_urls"].append(f"samples/{name}-{i}.safe.png")
        lines.append(json.dumps(event, ensure_ascii=False))
    (SAMPLES / f"{name}.ndjson").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"recorded {name}: {lines[-1][:160]}", flush=True)


if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor

    from . import meta

    import sys

    assert meta.client, "recording needs MODEL_API_KEY (run with --env-file .env)"
    names = sys.argv[1:] or list(SOURCES)
    with ThreadPoolExecutor(len(names)) as pool:
        list(pool.map(record, names))
