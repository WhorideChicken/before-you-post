# Before You Post

Find the personal info hidden in a photo (shipping labels, name tags, plates, screens, location clues,
GPS metadata) and remove it before posting. Muse Spark finds it, SAM 3.1 outlines it, Muse Image erases it,
and the edit is composited back only inside the mask, so the rest of the photo is pixel-identical.

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

Open http://localhost:8000. Without a key, detection returns mock findings and "erase" uses OpenCV inpainting.

Self-check (edits never touch pixels outside the mask): `uv run python -m app.pipeline`

## Layout

- `app/meta.py` — Meta Model API calls (Spark detection, SAM segmentation, Muse Image erase)
- `app/pipeline.py` — masks, blur/pixelate/inpaint, mask-bounded compositing
- `app/main.py` — `/api/detect`, `/api/apply`; stateless, nothing written to disk
- `static/index.html` — the whole UI
