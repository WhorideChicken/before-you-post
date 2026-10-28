"""Recorded agent runs for the sample gallery: real results that play instantly and cost no API calls.

Record (needs MODEL_API_KEY): uv run --env-file .env python -m app.samples [name ...]
"""
import asyncio
import base64
import functools
import json
import shutil
import time
from pathlib import Path

SAMPLES = Path(__file__).parent.parent / "static" / "samples"
BENCH = Path(__file__).parent.parent / "bench" / "images"
# sample name -> LeakBench photos, served as static/samples/{name}-{1..n}.jpg. Several photos = one account scan.
SOURCES = {"desk": ["desk_parcel"], "front_door": ["front_door"],
           "inj_poster": ["inj_poster"], "account": ["acct_cup", "acct_class", "acct_town"],
           "desk_private": ["desk_parcel"], "kr_market": ["kr_market"], "kr_school": ["kr_school"],
           "kr_moving": ["kr_moving"],
           # An imported Instagram export: more than six posts, so attacked one by one and linked (meta.MAX_TOGETHER)
           "export": ["ctrl_food", "acct_yuna_cake", "ctrl_landscape", "acct_yuna_notes", "ctrl_desk", "kr_moving",
                      "acct_yuna_shirt", "ctrl_brand"]}
PRIVATE = {"desk_private"}  # recorded in private mode: Muse Spark Open, edits on the server
# What each post would say. Captions often name what the photo's edits hide. Fictional, like the photos.
CAPTIONS = {
    "kr_market": "에어프라이어 팝니다 (6개월 사용) 🍟 직거래는 솔빛로 88 앞에서 가능해요 #중고거래",
    "kr_school": "우리 딸 드디어 초등학생 🌸 1학년 3반 친구들이랑 잘 지내자! #입학식 #해오름초등학교 #한별시맘",
    "kr_moving": "이사 끝! 🏠 별빛타워 보이는 집으로 왔어요. 집들이는 다음 주에 🙌 #새집 #한별시",
    "export": ["오늘 저녁은 파스타 🍝", "생일 축하해줘서 고마워 💕 #생일", "주말 산책 🌿", "실습 3주차.. 오늘도 버틴다 🩺",
               "과제 지옥 📚", "드디어 이사 끝 🏠 #새집 #집들이", "완주 기념 🏃‍♀️ #마라톤 #첫완주", "이거 진짜 맛있음 😋"],
}
SPEEDUP = 4


def captions(name: str) -> list[str]:
    """One per photo of the sample: a single string is the first photo's caption."""
    c = CAPTIONS.get(name, "")
    return list(c) if isinstance(c, list) else [c]


async def replay(name: str, first: str = "", speed: float = SPEEDUP):
    """Yield `first`, then the recorded NDJSON lines, paced like the real run but `speed` times faster.
    Async so a replay waits without holding one of the server's worker threads."""
    yield first
    prev = 0.0
    for line in (SAMPLES / f"{name}.ndjson").read_text(encoding="utf-8").splitlines():
        t = json.loads(line)["t"]
        await asyncio.sleep(min(max(t - prev, 0.0) / speed, 30.0 / speed))
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
    events = agent.run(imgs, attack=functools.partial(meta.attack, private=private), private=private,
                       read=functools.partial(meta.read_text, private=private, effort=meta.ATTACK_EFFORT),
                       caption=captions(name), rewrite=functools.partial(meta.rewrite_caption, private=private))
    for event in events:
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

    names = sys.argv[1:] or list(SOURCES)
    assert meta.client, "recording needs MODEL_API_KEY (run with --env-file .env)"
    assert meta.open_client or not PRIVATE & set(names), "private samples need OPEN_API_KEY too"
    with ThreadPoolExecutor(len(names)) as pool:
        list(pool.map(record, names))
