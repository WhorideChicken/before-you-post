"""Account LeakBench: is a combination spread across posts broken?

Each account is three staged photos ([accounts.json](accounts.json)). Each photo holds one piece, such as a first name,
a kind of job or a town, that is harmless alone and identifying together. Scored like LeakBench, without trusting the
attacker: a separate transcription pass reads the pieces before and after, and the combination counts as broken when
at least one piece that was legible is gone from the final photos.

The agent runs on the same photos twice: one photo at a time, which is what a single-photo checker does, and as one
account, which attacks all three together.

Usage: uv run --env-file .env python -m bench.accountbench [--force] [--private] [--only id,id]
"""
import argparse
import base64
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from app import agent, meta, pipeline
from bench import leakbench
from bench.leakbench import IMAGES, changed, legible, transcribe

ROOT = Path(__file__).parent
RESULTS = ROOT / "results" / "accounts"
PRIVATE = False


def finals(events) -> list[np.ndarray]:
    return [np.asarray(Image.open(io.BytesIO(base64.b64decode(b))).convert("RGB")) for b in events[-1]["images"]]


def attack(imgs):
    return meta.attack(imgs, private=PRIVATE)


def score(originals, outs, verified, events_list):
    texts = [t for img in outs for t in transcribe(img)]
    survived = legible(verified, texts)
    edits = [d for events in events_list for e in events if e["type"] == "edits" for d in e["edits"]]
    return {"survived": survived, "broken": len(verified) >= 2 and len(survived) < len(verified),
            "edits": [f"{d['action']}:{d['label']}" for d in edits],
            "photos_changed": sum(changed(a, b) > 0.001 for a, b in zip(originals, outs)),
            "changed": round(float(np.mean([changed(a, b) for a, b in zip(originals, outs)])), 4)}


def evaluate(account: dict) -> dict:
    imgs = [pipeline.load_image((IMAGES / f"{p['id']}.jpg").read_bytes())[0] for p in account["photos"]]
    rec = {"id": account["id"], "secrets": account["secrets"]}
    rec["verified"] = legible(account["secrets"], [t for img in imgs for t in transcribe(img)])

    t = time.time()
    with ThreadPoolExecutor(len(imgs)) as pool:
        alone = list(pool.map(lambda img: list(agent.run([img], attack=attack, private=PRIVATE)), imgs))
    rec["single_seconds"] = round(time.time() - t, 1)
    rec["single_worst_before"] = [max(next(e for e in ev if e["type"] == "attack")["exposure"].values(), default=0)
                                  for ev in alone]
    rec["single"] = score(imgs, [finals(ev)[0] for ev in alone], rec["verified"], alone)

    t = time.time()
    together = list(agent.run(imgs, attack=attack, private=PRIVATE))
    rec["account_seconds"] = round(time.time() - t, 1)
    rec["account_worst_before"] = max(next(e for e in together if e["type"] == "attack")["exposure"].values(), default=0)
    rec["account_safe"] = together[-1]["safe"]
    rec["account"] = score(imgs, finals(together), rec["verified"], [together])
    return rec


def run_account(account: dict, force: bool) -> dict:
    path = RESULTS / "scenes" / f"{account['id']}.json"
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        rec = evaluate(account)
    except Exception as e:
        rec = {"id": account["id"], "error": f"{type(e).__name__}: {e}"}
    else:
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{account['id']}: {'error ' + rec['error'] if 'error' in rec else 'ok'}", flush=True)
    return rec


def summarize(recs: list[dict]) -> str:
    ok = [r for r in recs if "error" not in r]
    n = len(ok)
    mode = "private mode (Muse Spark Open, edits on the server)" if PRIVATE else "standard mode"
    cost = sum(leakbench.usage[k] * leakbench.PRICE[k] for k in leakbench.usage)

    def total(key, field):
        return sum(len(r[key][field]) if isinstance(r[key][field], list) else r[key][field] for r in ok)

    lines = [
        f"# Account LeakBench ({time.strftime('%Y-%m-%d')}, {mode})", "",
        f"{n} staged accounts of 3 photos, {len(recs) - n} errors. In each, one photo shows a first name, one a kind of "
        "job or routine, one a town: harmless alone, identifying together. A combination is broken when at least one "
        "of its legible pieces is gone from the final photos, as read by a separate transcription pass.", "",
        "| | One photo at a time | As one account |", "|---|---|---|",
        f"| Combinations broken | {sum(r['single']['broken'] for r in ok)}/{n} | {sum(r['account']['broken'] for r in ok)}/{n} |",
        f"| Edits made | {total('single', 'edits')} | {total('account', 'edits')} |",
        f"| Photos changed | {total('single', 'photos_changed')}/{3 * n} | {total('account', 'photos_changed')}/{3 * n} |",
        f"| Share of each photo changed (mean) | {100 * np.mean([r['single']['changed'] for r in ok]):.1f}% "
        f"| {100 * np.mean([r['account']['changed'] for r in ok]):.1f}% |",
        f"| Time per account (mean, the three single runs in parallel) | {np.mean([r['single_seconds'] for r in ok]):.0f} s "
        f"| {np.mean([r['account_seconds'] for r in ok]):.0f} s |",
        "", f"Whole run cost (estimate, including the verifier): ${cost:.2f}", "", "## Per account", "",
        "| Account | Pieces legible | Worst exposure, each photo alone | Worst exposure together | One at a time | As one account |",
        "|---|---|---|---|---|---|",
    ]
    for r in recs:
        if "error" in r:
            lines.append(f"| {r['id']} | error: {r['error'][:80]} | | | | |")
            continue

        def cell(s):
            return f"{'broken' if s['broken'] else 'intact'}, {len(s['edits'])} edit(s): {', '.join(s['edits']) or '-'}"
        lines.append(f"| {r['id']} | {len(r['verified'])}/{len(r['secrets'])} | {r['single_worst_before']} "
                     f"| {r['account_worst_before']} | {cell(r['single'])} | {cell(r['account'])} |")
    return "\n".join(lines) + "\n"


def main():
    global PRIVATE, RESULTS
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    assert meta.client, "the verifier needs MODEL_API_KEY (run with --env-file .env)"
    if args.private:
        assert meta.open_client, "--private needs OPEN_API_KEY"
        PRIVATE, RESULTS = True, RESULTS / "private"
    leakbench.track_usage()
    (RESULTS / "scenes").mkdir(parents=True, exist_ok=True)
    accounts = json.loads((ROOT / "accounts.json").read_text(encoding="utf-8"))
    if args.only:
        accounts = [a for a in accounts if a["id"] in args.only.split(",")]
    with ThreadPoolExecutor(3) as pool:
        recs = list(pool.map(lambda a: run_account(a, args.force), accounts))
    summary = summarize(recs)
    if not args.only:
        (RESULTS / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
