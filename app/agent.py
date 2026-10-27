"""The red-team loop: attack -> plan the cheapest edits that block every risky inference -> edit -> re-attack."""
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations

import numpy as np

from . import meta, pipeline

log = logging.getLogger("uvicorn.error")

TARGET = 1  # highest level allowed after editing: a country, a first name, a type of school
COST = {"low": 1, "medium": 3, "high": 9}  # removal_impact -> how much an edit is allowed to hurt the photo
MAX_ATTACKS = 3  # attack, then at most two rounds of edit + re-attack
EXACT_LIMIT = 16  # exact search is 2^n subsets


def plan(graph: dict, target: int = TARGET) -> tuple[list[str], list[dict]]:
    """Minimum-cost set of editable clues that breaks every way to reach a level above target.

    A way needs all of its clues together, so removing any one of them blocks it (a hitting set).
    Returns the clue ids to edit, and the risky ways nothing can block because none of their clues has a box.
    """
    clues = {c["id"]: c for c in graph["clues"]}
    ways = [w for inf in graph["inferences"] for w in inf["ways"] if w["level"] > target]
    editable = {i for i, c in clues.items() if c["box"]}
    stuck = [w for w in ways if not editable & set(w["clues"])]
    ways = [set(w["clues"]) & editable for w in ways if editable & set(w["clues"])]
    if not ways:
        return [], stuck
    candidates = sorted(set().union(*ways))

    def cost(s):
        return sum(COST[clues[i]["removal_impact"]] for i in s), len(s)

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
            best.add(max(candidates, key=lambda i: sum(i in w for w in open_ways) / COST[clues[i]["removal_impact"]]))
    return sorted(best), stuck


def _mask(img: np.ndarray, item: dict) -> tuple[np.ndarray, str]:
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


def apply_edits(img: np.ndarray, items: list[dict]) -> tuple[np.ndarray, list[dict]]:
    """items: {label, box (0-1), action}. Model calls run in parallel on the same input; each result is
    composited only inside its own mask, so pixels outside every mask are untouched."""
    pad = max(3, max(img.shape[:2]) // 200)
    with ThreadPoolExecutor(8) as pool:
        masks = list(pool.map(lambda it: _mask(img, it), items))
        generated = list(pool.map(lambda it: _generate(img, it), items))
    out, done = img, []
    for item, (mask, source), gen in zip(items, masks, generated):
        mask = pipeline.grow(mask, pad)
        if not mask.any():
            continue
        if item["action"] in ("erase", "replace"):
            edited, engine = (gen, "muse-image") if gen is not None else (pipeline.inpaint(out, mask), "inpaint")
        else:
            edited, engine = getattr(pipeline, item["action"])(out), item["action"]
        out = pipeline.composite(out, edited, mask)
        done.append({**item, "mask": source, "engine": engine})
    return out, done


def run(img: np.ndarray, attack=meta.attack, target: int = TARGET):
    """Yield progress events for the UI. The last event carries the final PNG (lossless, metadata-free)."""
    current, before, edited_labels = img, None, set()
    for n in range(1, MAX_ATTACKS + 1):
        yield {"type": "status", "text": "Attacking the photo" if n == 1 else "Re-attacking the edited photo"}
        graph = attack(current)
        exposure = meta.exposure(graph)
        before = before if before is not None else exposure
        yield {"type": "attack", "round": n, "graph": graph, "exposure": exposure}
        ids, stuck = plan(graph, target)
        if not ids or n == MAX_ATTACKS:
            break
        items = []
        for c in graph["clues"]:
            if c["id"] in ids:
                # A clue that survived an earlier generative edit gets the edit that cannot fail.
                action = "pixelate" if c["label"].lower() in edited_labels else c["suggested"]
                items.append({"id": c["id"], "label": c["label"], "box": c["box"], "action": action})
        yield {"type": "plan", "round": n, "clues": ids, "stuck": len(stuck),
               "text": f"Breaking {len([w for i in graph['inferences'] for w in i['ways'] if w['level'] > target])} "
                       f"ways in with {len(items)} edit{'s' if len(items) != 1 else ''}"}
        current, done = apply_edits(current, items)
        edited_labels |= {it["label"].lower() for it in done}
        yield {"type": "edits", "round": n, "edits": done}
    yield {"type": "done", "before": before, "after": exposure, "residual": len(stuck),
           "image": base64.b64encode(pipeline.encode_png(current)).decode()}


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
    assert plan(g, target=4) == ([], [])

    # Offline loop: mock attack, box masks, inpaint/pixelate; converges after one round of edits.
    img = np.random.default_rng(0).integers(0, 256, (300, 400, 3), dtype=np.uint8)
    events = list(run(img, attack=meta.mock_attacker()))
    kinds = [e["type"] for e in events]
    assert kinds == ["status", "attack", "plan", "edits", "status", "attack", "done"], kinds
    done = events[-1]
    assert done["before"] == {"home_location": 4, "identity": 3} and done["after"] == {}
    assert [e["engine"] for e in events[3]["edits"]] == ["inpaint", "pixelate", "inpaint"]
    print("agent ok")
