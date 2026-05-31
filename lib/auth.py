"""
Auth helper รอบ streamlit-authenticator

- โหลด credentials จาก auth_config.yaml
- ทำ login UI ที่หน้า app.py
- ป้องกัน page อื่นด้วย session_state
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
import streamlit_authenticator as stauth
import yaml

from lib.config import (
    AUTH_CONFIG_PATH,
    COOKIE_NAME,
    COOKIE_KEY,
    COOKIE_EXPIRY_DAYS,
)


def _load_config() -> dict:
    path = Path(AUTH_CONFIG_PATH)
    if not path.exists():
        st.error(
            f"❌ ไม่พบไฟล์ auth config: `{path}`\n\n"
            "ก๊อปปี้ `auth_config.yaml.example` → `auth_config.yaml` "
            "แล้วสร้าง user/password (ดู `docs/auth_setup.md`)"
        )
        st.stop()
    with open(path) as f:
        return yaml.safe_load(f)


def _authenticator() -> stauth.Authenticate:
    """
    Note: ไม่ใช้ @st.cache_resource เพราะ stauth.Authenticate ใช้ widget ภายใน
    (จะ trigger CachedWidgetWarning). object เบามาก สร้างใหม่ทุก rerun ได้.
    """
    cfg = _load_config()
    return stauth.Authenticate(
        cfg["credentials"],
        COOKIE_NAME,
        COOKIE_KEY,
        COOKIE_EXPIRY_DAYS,
    )


def login_or_stop() -> None:
    """แสดงหน้า login. ถ้ายังไม่ login → st.stop()."""
    auth = _authenticator()
    auth.login(location="main", fields={"Form name": "เข้าสู่ระบบ",
                                        "Username": "ชื่อผู้ใช้",
                                        "Password": "รหัสผ่าน",
                                        "Login": "ลงชื่อเข้าใช้"})

    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
        st.stop()
    if status is None:
        st.warning("กรุณาเข้าสู่ระบบ")
        st.stop()


def current_user() -> dict[str, Any]:
    """คืนข้อมูล user ปัจจุบัน (name, username, role)."""
    cfg = _load_config()
    username = st.session_state.get("username", "")
    user_data = cfg["credentials"]["usernames"].get(username, {})
    return {
        "username": username,
        "name": st.session_state.get("name", ""),
        "role": user_data.get("role", "user"),
    }


def logout_button(label: str = "ออกจากระบบ", location: str = "sidebar") -> None:
    _authenticator().logout(label, location=location)


def require_auth() -> None:
    """เรียกตอนต้นของแต่ละ page เพื่อกัน user ที่ยังไม่ login."""
    if not st.session_state.get("authentication_status"):
        st.warning("กรุณาเข้าสู่ระบบที่หน้าหลักก่อน")
        st.page_link("app.py", label="ไปหน้าหลัก", icon="🏠")
        st.stop()


def require_role(*roles: str) -> None:
    """กัน page เฉพาะบาง role (เช่น admin only)."""
    require_auth()
    user = current_user()
    if user["role"] not in roles:
        st.error(f"❌ หน้านี้สำหรับ {', '.join(roles)} เท่านั้น (role ของคุณ: {user['role']})")
        st.stop()
