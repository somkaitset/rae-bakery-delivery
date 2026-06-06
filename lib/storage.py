"""
Local image storage — keep product/stock images on the machine's local disk
(Proxmox LXC).

Why not Google Drive: the Service Account has no storage quota, so it cannot
upload to an ordinary My Drive (403 storageQuotaExceeded), and the account is a
personal Gmail, so a Shared Drive is unavailable -> store locally and let
Streamlit render via st.image(path).

Only the bare "filename" is stored in the Sheet (not a full path) for
portability: moving machines / changing the path only needs a new IMAGES_DIR
env var; the stored data does not change.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image, ImageOps

from lib.config import IMAGE_JPEG_QUALITY, IMAGE_MAX_SIDE, IMAGES_DIR


# mime -> file extension (in case st.file_uploader sends png/webp)
_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _ext_for(mime_type: str | None, fallback: str = ".jpg") -> str:
    if mime_type:
        ext = _EXT_BY_MIME.get(mime_type.lower().strip())
        if ext:
            return ext
    fb = (fallback or "").lower()
    return fb if fb in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"


def _sanitize_stem(stem: str) -> str:
    """Strip the path, replace whitespace with _, keep only letters/digits/Thai/._- ."""
    stem = Path(stem).name  # guard against path traversal — keep the filename only
    stem = re.sub(r"\s+", "_", stem.strip())
    # Keep: letters/digits (\w), dot, dash, and the whole Thai Unicode block
    # (U+0E00–U+0E7F covers the vowels/tone marks that \w drops).
    stem = re.sub(r"[^\w.\-฀-๿]", "", stem, flags=re.UNICODE)
    return stem or "img"


def _process_image(content: bytes) -> tuple[bytes, str] | None:
    """
    Downscale + fix EXIF rotation + re-encode to JPEG.
    Returns (bytes, ".jpg") on success, or None if the image can't be opened
    (so the caller can fall back to the raw bytes).
    """
    try:
        img = Image.open(io.BytesIO(content))
        img = ImageOps.exif_transpose(img)               # rotate per phone-camera metadata
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")                      # flatten alpha/palette → JPEG
        img.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE))   # downscale (keep aspect, never upscale)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=IMAGE_JPEG_QUALITY, optimize=True)
        return buf.getvalue(), ".jpg"
    except Exception:
        return None


def save_image(name: str, content: bytes, mime_type: str | None = None) -> str:
    """
    Downscale + write to IMAGES_DIR, then return the "filename" to store in the Sheet.

    Args:
        name: the intended name (e.g. "product_โดนัท_P10001.jpg") — the extension
            is set from the actual result.
        content: raw image bytes from st.file_uploader.
        mime_type: used only on the fallback path (when the image can't be opened).

    Returns:
        the saved filename (basename), e.g. "product_โดนัท_P10001.jpg".
    """
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    stem = _sanitize_stem(Path(name).stem)
    processed = _process_image(content)
    if processed is not None:
        data, ext = processed
    else:
        data, ext = content, _ext_for(mime_type, fallback=Path(name).suffix)
    filename = f"{stem}{ext}"
    (IMAGES_DIR / filename).write_bytes(data)
    return filename


def image_src(value) -> str | None:
    """
    Convert the value stored in the Sheet into something st.image() can render.

    - empty → None
    - a URL (http/https/data:) → returned as-is (supports old Drive values)
    - a filename → resolved under IMAGES_DIR; returns the full path if the file
      exists, else None
    """
    s = str(value or "").strip()
    if not s:
        return None
    if s.startswith(("http://", "https://", "data:")):
        return s
    path = IMAGES_DIR / Path(s).name
    return str(path) if path.exists() else None


def delete_image(value) -> None:
    """Delete the local image file (skip URLs/empty; no error if the file is missing)."""
    s = str(value or "").strip()
    if not s or s.startswith(("http://", "https://", "data:")):
        return
    try:
        (IMAGES_DIR / Path(s).name).unlink(missing_ok=True)
    except OSError:
        pass
