"""
Local image storage — เก็บรูปสินค้า/รูปสต็อกไว้บน disk ของเครื่อง (Proxmox LXC)

ทำไมไม่ใช้ Google Drive: Service Account ไม่มี storage quota จึงอัปโหลดเข้า
My Drive ธรรมดาไม่ได้ (403 storageQuotaExceeded) และบัญชีเป็น personal Gmail
จึงใช้ Shared Drive ไม่ได้ → เก็บ local แล้วให้ Streamlit render ผ่าน st.image(path)

ค่าที่เก็บใน Sheet จะเป็น "ชื่อไฟล์" เท่านั้น (ไม่ใช่ path เต็ม) เพื่อให้พกพาได้:
ถ้าย้ายเครื่อง/เปลี่ยน path แค่ตั้ง env IMAGES_DIR ใหม่ ข้อมูลใน Sheet ไม่ต้องแก้
"""
from __future__ import annotations

import re
from pathlib import Path

from lib.config import IMAGES_DIR


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


def save_image(name: str, content: bytes, mime_type: str | None = None) -> str:
    """
    เขียน bytes ลง IMAGES_DIR แล้วคืน "ชื่อไฟล์" สำหรับเก็บลง Sheet

    Args:
        name: ชื่อที่ตั้งใจ (เช่น "product_โดนัท_P10001.jpg") — นามสกุลจะถูกแทนตาม mime จริง
        content: ข้อมูลรูป (bytes)
        mime_type: เช่น "image/png" จาก st.file_uploader

    Returns:
        ชื่อไฟล์ที่บันทึก (basename) เช่น "product_โดนัท_P10001.png"
    """
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    stem = _sanitize_stem(Path(name).stem)
    ext = _ext_for(mime_type, fallback=Path(name).suffix)
    filename = f"{stem}{ext}"
    (IMAGES_DIR / filename).write_bytes(content)
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
