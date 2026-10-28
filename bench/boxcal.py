"""How far off are the attacker's boxes? Each clue box is compared with SAM 3.1's outline of the same object, and a
per-axis linear correction (true = a * box + b) is fitted on half the photos and scored on the other half.

Usage: uv run --env-file .env python -m bench.boxcal [--private]
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from app import meta, pipeline

ROOT = Path(__file__).parent
IMAGES = ROOT / "images"


def pairs(name: str, private: bool) -> list[tuple]:
    img = pipeline.load_image((IMAGES / f"{name}.jpg").read_bytes())[0]
    h, w = img.shape[:2]
    out = []
    for c in meta.attack([img], private=private)["clues"]:
        if not c["box"]:
            continue
        mask = meta.segment(img, c["label"], c["box"])
        if mask is None or not mask.any():
            continue
        ys, xs = np.nonzero(mask)
        out.append((name, c["label"], c["box"], [xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h]))
    return out


def fit(ps):
    """Least squares per axis over both edges: x_true = a * x + b, y_true = c * y + d."""
    def axis(i):
        x = np.array([p[2][j] for p in ps for j in (i, i + 2)])
        y = np.array([p[3][j] for p in ps for j in (i, i + 2)])
        return tuple(np.linalg.lstsq(np.stack([x, np.ones_like(x)], 1), y, rcond=None)[0])
    return axis(0), axis(1)


def correct(box, cal):
    (a, b), (c, d) = cal
    return [a * box[0] + b, c * box[1] + d, a * box[2] + b, c * box[3] + d]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", action="store_true")
    args = ap.parse_args()
    names = [s["id"] for s in json.loads((ROOT / "scenes.json").read_text(encoding="utf-8"))]
    names += [s["id"] for s in json.loads((ROOT / "samples.json").read_text(encoding="utf-8"))]
    with ThreadPoolExecutor(4) as pool:
        per_photo = list(pool.map(lambda n: pairs(n, args.private), names))
    train = [p for i, ps in enumerate(per_photo) if i % 2 == 0 for p in ps]
    test = [p for i, ps in enumerate(per_photo) if i % 2 for p in ps]
    every = train + test
    cal = fit(train)

    def mean_iou(ps, f=lambda b: b):
        return np.mean([meta._iou(f(p[2]), p[3]) for p in ps])

    print(f"{'private' if args.private else 'standard'}: {len(every)} clue boxes with a SAM outline")
    print(f"mean IoU with SAM's outline: raw {mean_iou(every):.2f}; held-out photos raw {mean_iou(test):.2f}, "
          f"corrected {mean_iou(test, lambda b: correct(b, cal)):.2f}")
    print(f"fit on half: x = {cal[0][0]:.3f} x + {cal[0][1]:.3f}, y = {cal[1][0]:.3f} y + {cal[1][1]:.3f}")
    full = fit(every)
    print(f"fit on all:  x = {full[0][0]:.3f} x + {full[0][1]:.3f}, y = {full[1][0]:.3f} y + {full[1][1]:.3f}")
    errs = np.array([[p[2][j] - p[3][j] for j in range(4)] for p in every])
    print("mean edge error (box - outline) x0 y0 x1 y1:", np.round(errs.mean(0), 3), "sd", np.round(errs.std(0), 3))
    for p in every:
        print(f"  {p[0]:16} {p[1][:28]:28} box {np.round(p[2], 3)} sam {np.round(p[3], 3)} iou {meta._iou(p[2], p[3]):.2f}")


if __name__ == "__main__":
    main()
