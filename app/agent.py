"""The red-team loop: attack -> plan the cheapest edits that block every risky inference -> edit -> re-attack."""
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations

import numpy as np

from . import meta, pipeline

log = logging.getLogger("uvicorn.error")

# Highest level allowed after editing. "Narrowed" (a city, a type of workplace) is what any travel or food photo
# says; "specific" (a street, a named school, a full name) is where finding someone starts.
TARGET = 2
STRICT = {"contact": 1, "financial_or_id": 1}  # even part of a phone, card or ID number is too much
COST = {"low": 1, "medium": 3, "high": 9}  # removal_impact -> how much an edit is allowed to hurt the photo
LARGE = [(0.4, 50), (0.2, 9)]  # (share of the frame, minimum cost): repainting a whole view is a last resort
MAX_ATTACKS = 4  # attack, then at most three rounds of edit + re-attack
EXACT_LIMIT = 16  # exact search is 2^n subsets
ESCALATE = 0.3  # a clue at least this much inside an already-edited area gets the edit that cannot fail


def plan(graph: dict, target: int = TARGET) -> tuple[list[str], list[dict]]:
    """Minimum-cost set of editable clues that breaks every way to reach a level above target.

    A way needs all of its clues together, so removing any one of them blocks it (a hitting set).
    Returns the clue ids to edit, and the risky ways nothing can block because none of their clues has a box.
    """
    clues = {c["id"]: c for c in graph["clues"]}
    ways = risky_ways(graph, target)
    editable = {i for i, c in clues.items() if c["box"]}
    stuck = [w for w in ways if not editable & set(w["clues"])]
    ways = [set(w["clues"]) & editable for w in ways if editable & set(w["clues"])]
    if not ways:
        return [], stuck
    candidates = sorted(set().union(*ways))
    price = {i: clue_cost(clues[i]) for i in candidates}

    def cost(s):
        return sum(price[i] for i in s), len(s)

    def blocks_all(s):
        return all(w & s for w in ways)

    if len(candidates) <= EXACT_LIMIT:
        subsets = (set(c) for r in range(1, len(candidates) + 1) for c in combinations(candidates, r))
        best = min((s for s in subsets if blocks_all(s)), key=cost)
    else:
        # ponytail: greedy weighted set cover past EXACT_LIMIT clues; not guaranteed minimal.
        best = set()
        while not blocks_all(best):
            open_ways = [w for w in ways if not w & best]
            best.add(max(candidates, key=lambda i: sum(i in w for w in open_ways) / price[i]))
    return sorted(best), stuck


def risky_ways(graph: dict, target: int = TARGET) -> list[dict]:
    return [w for inf in graph["inferences"] for w in inf["ways"]
            if w["level"] > min(target, STRICT.get(inf["category"], target))]


def clue_cost(clue: dict) -> int:
    """The attacker's own estimate of how much hiding it hurts, floored by how much of the frame it covers."""
    x0, y0, x1, y1 = clue["box"]
    area = (x1 - x0) * (y1 - y0)
    return max([COST[clue["removal_impact"]]] + [c for share, c in LARGE if area >= share])


def _mask(img: np.ndarray, item: dict) -> tuple[np.ndarray, str]:
    """SAM's outline when it finds the object, else the attacker's box. Not both: Spark's boxes can sit off the
    object, and a generative edit composited into that stray area can paint in things that were never there."""
    try:
        mask = meta.segment(img, item["label"], item["box"])
    except Exception:
        log.exception("SAM segmentation failed, falling back to the box")
        mask = None
    return (mask, "sam") if mask is not None else (pipeline.box_mask(img.shape, item["box"]), "box")


def _generate(img: np.ndarray, item: dict) -> np.ndarray | None:
    if item["action"] not in ("erase", "replace"):
        return None
    try:
        return meta.edit(img, item["label"], item["action"])
    except Exception:
        log.exception("Muse Image edit failed, falling back to inpaint")
        return None


def apply_edits(img: np.ndarray, items: list[dict]) -> tuple[np.ndarray, list[dict], np.ndarray]:
    """items: {label, box (0-1), action}. Model calls run in parallel on the same input; each result is
    composited only inside its own mask, so pixels outside every mask are untouched.
    Returns the edited image, what was done, and the union of all masks."""
    pad = max(3, max(img.shape[:2]) // 200)
    with ThreadPoolExecutor(8) as pool:
        masks = list(pool.map(lambda it: _mask(img, it), items))
        generated = list(pool.map(lambda it: _generate(img, it), items))
    out, done, union = img, [], np.zeros(img.shape[:2], bool)
    for item, (mask, source), gen in zip(items, masks, generated):
        mask = pipeline.grow(mask, pad)
        if not mask.any():
            continue
        if item["action"] in ("erase", "replace"):
            edited, engine = (gen, "muse-image") if gen is not None else (pipeline.inpaint(out, mask), "inpaint")
        else:
            edited, engine = getattr(pipeline, item["action"])(out), item["action"]
        out = pipeline.composite(out, edited, mask)
        union |= mask
        done.append({**item, "mask": source, "engine": engine})
    return out, done, union


def run(imgs: list[np.ndarray], attack=meta.attack, target: int = TARGET):
    """Yield progress events for the UI. One photo, or several from one account attacked together: the planner then
    breaks combinations across photos with the fewest edits overall. Image fields are lists in photo order, None for
    a photo a step left unchanged. The last event carries the final PNGs (lossless, metadata-free)."""
    current, before = list(imgs), None
    edited = [np.zeros(img.shape[:2], bool) for img in imgs]
    for n in range(1, MAX_ATTACKS + 1):
        what = "photo" if len(imgs) == 1 else f"{len(imgs)} photos together"
        yield {"type": "status", "text": f"Attacking the {what}" if n == 1 else f"Re-attacking the edited {what}"}
        graph = attack(current)
        exposure = meta.exposure(graph)
        before = before if before is not None else exposure
        yield {"type": "attack", "round": n, "graph": graph, "exposure": exposure}
        ids, stuck = plan(graph, target)
        if not ids or n == MAX_ATTACKS:
            break
        items = {}  # photo index -> edits
        for c in graph["clues"]:
            if c["id"] in ids:
                p = c["photo"]
                # A clue found again where we already edited survived a generative edit: use one that cannot fail.
                box = pipeline.box_mask(imgs[p].shape, c["box"])
                action = "pixelate" if (box & edited[p]).sum() >= ESCALATE * box.sum() else c["suggested"]
                items.setdefault(p, []).append({"id": c["id"], "photo": p, "label": c["label"], "box": c["box"],
                                                "action": action})
        count = sum(map(len, items.values()))
        yield {"type": "plan", "round": n, "clues": ids, "stuck": len(stuck),
               "text": f"Breaking {len(risky_ways(graph, target))} ways in with {count} edit{'s' if count != 1 else ''}"}
        if n == 1:
            # Something to look at while the real edits run: the planned clues pixelated, with a wide margin since
            # Spark's boxes can sit a little off. Display only; the download is always the re-checked result.
            preview = [None] * len(imgs)
            for p, its in items.items():
                img, area = imgs[p], np.zeros(imgs[p].shape[:2], bool)
                for it in its:
                    area |= pipeline.box_mask(img.shape, it["box"])
                area = pipeline.grow(area, max(img.shape[:2]) // 30)
                preview[p] = pipeline.encode_jpeg_b64(pipeline.composite(img, pipeline.pixelate(img), area))
            yield {"type": "preview", "images": preview}
        with ThreadPoolExecutor(len(items)) as pool:
            results = dict(zip(items, pool.map(lambda p: apply_edits(current[p], items[p]), items)))
        done = []
        for p, (out, did, mask) in results.items():
            current[p] = out
            edited[p] |= mask
            done += did
        yield {"type": "edits", "round": n, "edits": done,
               "images": [pipeline.encode_jpeg_b64(current[p]) if p in results else None for p in range(len(imgs))]}
    yield {"type": "done", "before": before, "after": exposure, "residual": len(stuck), "safe": not ids and not stuck,
           "images": [base64.b64encode(pipeline.encode_png(img)).decode() for img in current]}


if __name__ == "__main__":
    def clue(i, impact):
        return {"id": i, "box": [0.1, 0.1, 0.2, 0.2], "label": i, "removal_impact": impact, "suggested": "erase"}

    def way(ids, level):
        return {"clues": ids, "level": level, "confidence": "high"}

    # The cheap cut is c1 + c3; blocking c2 and c4 instead costs far more.
    g = {"clues": [clue("c1", "low"), clue("c2", "high"), clue("c3", "medium"), clue("c4", "high")],
         "inferences": [{"category": "home_location", "level": 4, "ways": [way(["c1"], 4), way(["c2", "c3"], 3)]},
                        {"category": "identity", "level": 3, "ways": [way(["c3", "c4"], 3), way(["c2"], 1)]}]}
    assert plan(g) == (["c1", "c3"], [])
    # A risky way whose only clue cannot be edited is reported, not silently dropped.
    g["clues"].append({**clue("c5", "low"), "box": None})
    g["inferences"].append({"category": "contact", "level": 4, "ways": [way(["c5"], 4)]})
    ids, stuck = plan(g)
    assert ids == ["c1", "c3"] and len(stuck) == 1
    assert plan(g, target=4) == ([], stuck), "contact stays strict even with a lax target"
    # Repainting most of the frame is the last resort, whatever the attacker estimated.
    big = {**clue("view", "low"), "box": [0.0, 0.0, 0.8, 0.8]}
    g2 = {"clues": [big, clue("sign", "medium")],
          "inferences": [{"category": "home_location", "level": 3, "ways": [way(["view", "sign"], 3)]}]}
    assert clue_cost(big) == 50 and plan(g2) == (["sign"], [])

    # Offline loop: mock attack, box masks, inpaint/pixelate; converges after one round of edits.
    img = np.random.default_rng(0).integers(0, 256, (300, 400, 3), dtype=np.uint8)
    events = list(run([img], attack=meta.mock_attacker()))
    kinds = [e["type"] for e in events]
    assert kinds == ["status", "attack", "plan", "preview", "edits", "status", "attack", "done"], kinds
    done = events[-1]
    assert done["before"] == {"home_location": 4, "identity": 3} and done["after"] == {} and done["safe"]
    assert [e["engine"] for e in events[4]["edits"]] == ["inpaint", "pixelate", "inpaint"]

    # Account scan: a name tag in photo 1 and a street sign in photo 2 are harmless alone, risky together. One edit
    # in the cheaper photo breaks it, and the other photo comes back byte-identical.
    tag, sign = meta.MOCK_ATTACK["clues"][1], meta.MOCK_ATTACK["clues"][2]
    pair = {"clues": [{**tag, "photo": 1, "removal_impact": "high"}, {**sign, "photo": 2, "removal_impact": "low"}],
            "inferences": [{"category": "identity", "reasoning": "", "ways": [
                way(["c2"], 1), way(["c3"], 2), way(["c2", "c3"], 3)]}], "summary": ""}
    graphs = iter([pair])
    imgs = [img, img[::-1].copy()]
    events = list(run(imgs, attack=lambda ims: meta.normalize(next(graphs, meta.MOCK_CLEAN), len(ims))))
    edits = next(e for e in events if e["type"] == "edits")
    assert [(d["id"], d["photo"]) for d in edits["edits"]] == [("c3", 1)] and edits["images"][0] is None
    done = events[-1]
    assert done["safe"] and done["images"][0] == base64.b64encode(pipeline.encode_png(imgs[0])).decode()
    assert done["images"][1] != base64.b64encode(pipeline.encode_png(imgs[1])).decode()
    print("agent ok")
