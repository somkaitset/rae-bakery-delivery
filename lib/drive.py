"""
Google Drive client — อัปโหลดรูปสินค้า/รูปสต็อก/บิล PDF
"""
from __future__ import annotations

import io
import mimetypes
from functools import lru_cache

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from lib.config import GOOGLE_SERVICE_ACCOUNT_PATH, SUBFOLDER_ID


SCOPES = ["https://www.googleapis.com/auth/drive"]


@lru_cache(maxsize=1)
def _service():
    creds = Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_PATH, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_bytes(
    name: str,
    content: bytes,
    folder_id: str | None = None,
    mime_type: str | None = None,
    public: bool = True,
) -> dict:
    """
    อัปโหลดไฟล์จาก bytes ไปยัง Drive

    Returns:
        dict ที่มี: id, name, webViewLink, webContentLink (downloadable link)
    """
    folder_id = folder_id or SUBFOLDER_ID
    if not mime_type:
        mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"

    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type)
    file = (
        _service()
        .files()
        .create(
            body={"name": name, "parents": [folder_id]},
            media_body=media,
            fields="id, name, webViewLink, webContentLink",
        )
        .execute()
    )

    if public:
        make_public(file["id"])
        # ใช้ thumbnail link เพื่อให้ Streamlit แสดงรูปได้ตรง
        file["thumbnail_url"] = f"https://drive.google.com/thumbnail?id={file['id']}&sz=w400"

    return file


def make_public(file_id: str) -> None:
    """ตั้งสิทธิ์ให้ใครก็ตามที่มีลิงก์เปิดดูได้."""
    _service().permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()


def find_or_create_subfolder(name: str, parent_id: str | None = None) -> str:
    """หาโฟลเดอร์ย่อยตามชื่อ (ใต้ parent_id) ถ้าไม่มีให้สร้างใหม่ คืน folder id."""
    parent_id = parent_id or SUBFOLDER_ID
    q = (
        f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents and trashed = false"
    )
    results = _service().files().list(q=q, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    folder = (
        _service()
        .files()
        .create(
            body={
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            },
            fields="id",
        )
        .execute()
    )
    return folder["id"]
