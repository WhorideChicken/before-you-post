"""A fictional Instagram export to try the import with: static/samples/demo-instagram-export.zip.

Same layout as Instagram's "Download your information" (posts_1.json next to media/posts/...), including how it
writes text: UTF-8 bytes escaped as Latin-1 characters. Photos and captions are the "export" sample's.

Usage: uv run python -m bench.demo_export
"""
import json
import zipfile
from pathlib import Path

from app import samples

OUT = samples.SAMPLES / "demo-instagram-export.zip"


def main():
    posts, start = [], 1777000000  # spring 2026, a day apart
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for i, (source, caption) in enumerate(zip(samples.SOURCES["export"], samples.CAPTIONS["export"])):
            uri = f"media/posts/202604/1790000{i:04d}.jpg"
            z.write(samples.BENCH / f"{source}.jpg", uri)
            posts.append({"media": [{"uri": uri, "creation_timestamp": start + i * 86400,
                                     "title": caption.encode("utf-8").decode("latin-1")}]})
        z.writestr("your_instagram_activity/content/posts_1.json", json.dumps(posts, indent=2))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(posts)} posts)")


if __name__ == "__main__":
    main()
