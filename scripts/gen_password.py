"""
สร้าง bcrypt hash ของรหัสผ่าน เพื่อใส่ใน auth_config.yaml

ใช้:
    .venv/bin/python scripts/gen_password.py <plaintext_password>

ตัวอย่าง:
    .venv/bin/python scripts/gen_password.py "MyP@ssw0rd"
    → $2b$12$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
"""
from __future__ import annotations

import sys

import bcrypt


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/gen_password.py <plaintext_password>")
        return 1
    password = sys.argv[1].encode()
    hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=12)).decode()
    print(hashed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
