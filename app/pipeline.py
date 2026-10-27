"""Pixel side of the pipeline: masks, edits and mask-bounded compositing. No model calls here."""
import io

import cv2
import numpy as np
from PIL import Image, ImageOps

ACTIONS = ("erase", "pixelate", "blur", "keep")


def load_image(data: bytes) -> tuple[np.ndarray, dict]:
    """Decode upload to an upright RGB array and report what the file's metadata leaks."""
    img = Image.open(io.BytesIO(data))
    exif = img.getexif()
    device = " ".join(str(v).strip() for v in (exif.get(0x010F), exif.get(0x0110)) if v)
    metadata = {"gps": bool(exif.get_ifd(0x8825)), "device": device or None}
    # Phone photos are stored sideways with an orientation tag; boxes are relative to the upright image.
    img = ImageOps.exif_transpose(img).convert("RGB")
    return np.asarray(img).copy(), metadata


def encode_png(img: np.ndarray) -> bytes:
    """Lossless and metadata-free, so untouched pixels stay byte-identical and EXIF/GPS never leaves."""
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "PNG")
    return buf.getvalue()


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
    print("pipeline ok")
