"""
Local image storage — เก็บรูปสินค้า/รูปสต็อกไว้บน disk ของเครื่อง (Proxmox LXC)

ทำไมไม่ใช้ Google Drive: Service Account ไม่มี storage quota จึงอัปโหลดเข้า
My Drive ธรรมดาไม่ได้ (403 storageQuotaExceeded) และบัญชีเป็น personal Gmail
จึงใช้ Shared Drive ไม่ได้ → เก็บ local แล้วให้ Streamlit render ผ่าน st.image(path)

ค่าที่เก็บใน Sheet จะเป็น "ชื่อไฟล์" เท่านั้น (ไม่ใช่ path เต็ม) เพื่อให้พกพาได้:
ถ้าย้ายเครื่อง/เปลี่ยน path แค่ตั้ง env IMAGES_DIR ใหม่ ข้อมูลใน Sheet ไม่ต้องแก้
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image, ImageOps

from lib.config import IMAGE_JPEG_QUALITY, IMAGE_MAX_SIDE, IMAGES_DIR


# mime → นามสกุลไฟล์ (เผื่อ st.file_uploader ส่ง png/webp มา)
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
    """ตัด path, แทนช่องว่างด้วย _, เก็บเฉพาะตัวอักษร/ตัวเลข/ไทย/._- ."""
    stem = Path(stem).name  # กัน path traversal — เอาเฉพาะชื่อไฟล์
    stem = re.sub(r"\s+", "_", stem.strip())
    # เก็บ: ตัวอักษร/ตัวเลข (\w), จุด, ขีด, และช่วง Unicode ไทยทั้งบล็อก
    # (U+0E00–U+0E7F ครอบสระ/วรรณยุกต์ที่ \w ตัดทิ้ง)
    stem = re.sub(r"[^\w.\-฀-๿]", "", stem, flags=re.UNICODE)
    return stem or "img"


def _process_image(content: bytes) -> tuple[bytes, str] | None:
    """
    ย่อรูป + แก้การหมุนตาม EXIF + เข้ารหัสใหม่เป็น JPEG
    คืน (bytes, ".jpg") ถ้าสำเร็จ, None ถ้าเปิดรูปไม่ได้ (ให้ caller fallback เป็น raw)
    """
    try:
        img = Image.open(io.BytesIO(content))
        img = ImageOps.exif_transpose(img)               # หมุนตาม metadata กล้องมือถือ
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")                      # flatten alpha/palette → JPEG
        img.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE))   # ย่อ (รักษาสัดส่วน, ไม่ขยาย)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=IMAGE_JPEG_QUALITY, optimize=True)
        return buf.getvalue(), ".jpg"
    except Exception:
        return None


def save_image(name: str, content: bytes, mime_type: str | None = None) -> str:
    """
    ย่อรูป + เขียนลง IMAGES_DIR แล้วคืน "ชื่อไฟล์" สำหรับเก็บลง Sheet

    Args:
        name: ชื่อที่ตั้งใจ (เช่น "product_โดนัท_P10001.jpg") — นามสกุลจะถูกตั้งตามผลจริง
        content: ข้อมูลรูปดิบ (bytes) จาก st.file_uploader
        mime_type: ใช้เฉพาะตอน fallback (เปิดรูปไม่ได้)

    Returns:
        ชื่อไฟล์ที่บันทึก (basename) เช่น "product_โดนัท_P10001.jpg"
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
    แปลงค่าที่เก็บใน Sheet ให้เป็นสิ่งที่ st.image() แสดงได้

    - ว่าง → None
    - เป็น URL (http/https/data:) → คืนตามเดิม (รองรับค่าเก่าจาก Drive)
    - เป็นชื่อไฟล์ → resolve ใต้ IMAGES_DIR, คืน path เต็มถ้าไฟล์มีอยู่จริง ไม่งั้น None
    """
    s = str(value or "").strip()
    if not s:
        return None
    if s.startswith(("http://", "https://", "data:")):
        return s
    path = IMAGES_DIR / Path(s).name
    return str(path) if path.exists() else None


def delete_image(value) -> None:
    """ลบไฟล์รูป local (ข้ามถ้าเป็น URL หรือค่าว่าง; ไม่ error ถ้าไฟล์ไม่มี)."""
    s = str(value or "").strip()
    if not s or s.startswith(("http://", "https://", "data:")):
        return
    try:
        (IMAGES_DIR / Path(s).name).unlink(missing_ok=True)
    except OSError:
        pass
