# Before You Post

A privacy red-team agent for your photos. It attacks a photo the way a determined stranger would, plans the
fewest edits that break every way to find you, makes them, and attacks again to check.

1. **Attack**: Muse Spark builds an exposure graph: clues (a shipping label, a street sign through the window,
   a badge) and the inferences they enable, each with every independent way to reach it and how precise it gets
   (broad, narrowed, specific, exact). It describes what is exposed but never prints the personal values.
2. **Plan**: a minimum-cost hitting set over those ways picks the cheapest clues to remove so nothing above
   "broad" can still be inferred.
3. **Edit**: SAM 3.1 outlines each clue, Muse Image replaces it with a blank version or erases it, and the result is
   composited back only inside the mask. Muse Image also changes pixels it was not asked to (7-12% of the frame
   in our tests); compositing keeps everything outside the masks pixel-identical.
4. **Re-attack**: Muse Spark attacks the edited photo. Anything still exposed goes through another round.

The safe copy is a lossless PNG with no EXIF or GPS data.

## Hackathon note

Built for the [Meta Global AI Developer Hackathon 2026](https://cerebralvalley.ai/e/meta-ai-developer-hackathon)
(Indie track, Oct 26 – Nov 4).

The first commit is a small skeleton written on Oct 26, before kickoff: photo upload, mock detection,
blur/pixelate/OpenCV inpainting, mask-bounded compositing, and untested request code for Muse Spark and
Muse Image (about 300 lines, no Meta model had been called yet). Everything after that commit was built
during the hackathon.

## Run

```bash
uv sync
cp .env.example .env   # add MODEL_API_KEY; leave it empty for offline demo mode
uv run --env-file .env uvicorn app.main:app --reload
```

Open http://localhost:8000 and press "Try a sample photo". Without a key the attack is a placeholder and edits use
OpenCV inpainting, so the whole loop still runs offline.

Self-checks: `uv run python -m app.pipeline`, `uv run python -m app.meta`, `uv run python -m app.agent`

Privacy note: while the Meta Model API account uses free hackathon credits, Meta may use submitted content for
product improvement. Test with staged photos, not real personal ones.

## Layout

- `app/agent.py`: the loop (attack, plan, edit, re-attack) and the hitting-set planner
- `app/meta.py`: Meta Model API calls (Muse Spark attacker, SAM 3.1 segmentation, Muse Image edits)
- `app/pipeline.py`: masks, blur/pixelate/inpaint, mask-bounded compositing
- `app/main.py`: `/api/run` streams the agent's progress as NDJSON; `/api/apply` applies manual edits. Stateless,
  nothing is written to disk.
- `static/index.html`: the whole UI. `static/samples/desk.jpg` is a staged scene generated with Muse Image; every
  name and address in it is fictional.
