"""Pixel side of the pipeline: masks, edits and mask-bounded compositing. No model calls here."""
import base64
import io

import cv2
import numpy as np
from PIL import Image, ImageOps

ACTIONS = ("erase", "pixelate", "blur", "keep")
# A small file can declare a huge canvas (a decompression bomb). JPEG decodes straight to a reduced size via draft(),
# so it may be big; anything else is decoded in full and must be small enough for a 512 MB host.
MAX_PIXELS = {"JPEG": 100_000_000, "MPO": 100_000_000, "PNG": 25_000_000, "WEBP": 25_000_000}


def load_image(data: bytes, max_side: int | None = None) -> tuple[np.ndarray, dict]:
    """Decode upload to an upright RGB array and report what the file's metadata leaks."""
    img = Image.open(io.BytesIO(data))
    if img.width * img.height > MAX_PIXELS.get(img.format, 0):
        raise ValueError(f"{img.format} {img.width}x{img.height} is not an accepted photo")
    if max_side:
        img.draft("RGB", (max_side, max_side))
    exif = img.getexif()
    device = " ".join(str(v).strip() for v in (exif.get(0x010F), exif.get(0x0110)) if v)
    metadata = {"gps": bool(exif.get_ifd(0x8825)), "device": device or None}
    # Phone photos are stored sideways with an orientation tag; boxes are relative to the upright image.
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    return np.asarray(img).copy(), metadata


def encode_png(img: np.ndarray) -> bytes:
    """Lossless and metadata-free, so untouched pixels stay byte-identical and EXIF/GPS never leaves."""
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "PNG")
    return buf.getvalue()


def encode_jpeg_b64(img: np.ndarray, quality: int = 82) -> str:
    """Small progress frames for the UI. The downloadable result stays the lossless PNG."""
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


def box_mask(shape, box) -> np.ndarray:
    """Normalized [x0, y0, x1, y1] -> boolean mask. Fallback when segmentation gives nothing."""
    h, w = shape[:2]
    x0, y0, x1, y1 = box
    mask = np.zeros((h, w), bool)
    mask[int(y0 * h):int(np.ceil(y1 * h)), int(x0 * w):int(np.ceil(x1 * w))] = True
    return mask


def grow(mask: np.ndarray, px: int) -> np.ndarray:
    """Pad the mask so edits cover anti-aliased edges the box or segment missed."""
    k = 2 * px + 1
    return cv2.dilate(mask.astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool)


def composite(orig: np.ndarray, edited: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Take edited pixels only inside the mask. Everything outside is the original, guaranteed."""
    return np.where(mask[..., None], edited, orig)


def blur(img: np.ndarray) -> np.ndarray:
    k = max(img.shape[:2]) // 25 | 1
    return cv2.GaussianBlur(img, (k, k), 0)


def pixelate(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    block = max(8, max(h, w) // 60)
    small = cv2.resize(img, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def inpaint(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Classic fill. Fine for small text and barcodes; large objects need the generative edit."""
    return cv2.inpaint(img, mask.astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)


if __name__ == "__main__":
    # Self-check for the core promise: edits never touch pixels outside their mask.
    rng = np.random.default_rng(0)
    orig = rng.integers(0, 256, (240, 320, 3), dtype=np.uint8)
    mask = grow(box_mask(orig.shape, (0.3, 0.3, 0.6, 0.5)), 3)
    for name, edited in [("blur", blur(orig)), ("pixelate", pixelate(orig)), ("inpaint", inpaint(orig, mask))]:
        out = composite(orig, edited, mask)
        assert np.array_equal(out[~mask], orig[~mask]), f"{name} changed pixels outside the mask"
        assert not np.array_equal(out[mask], orig[mask]), f"{name} left the masked area untouched"
    back, meta = load_image(encode_png(out))
    assert np.array_equal(back, out) and meta == {"gps": False, "device": None}
    # A 9000x9000 PNG is a few hundred KB on disk and 243 MB decoded: refused before decoding.
    bomb = io.BytesIO()
    Image.new("1", (9000, 9000)).save(bomb, "PNG")
    try:
        load_image(bomb.getvalue(), 2048)
        raise AssertionError("decompression bomb was decoded")
    except ValueError:
        pass
    print("pipeline ok")
