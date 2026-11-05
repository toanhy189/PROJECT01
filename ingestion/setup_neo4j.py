"""Chuẩn bị cấu hình Neo4j local, giữ nguyên các bí mật và cờ RAG đang có."""

import re
import secrets

from dotenv import dotenv_values

from backend.core.config import ROOT


def prepare_environment() -> None:
    """Chỉ tạo mật khẩu nếu chưa có; không in thông tin xác thực ra terminal."""
    path = ROOT / ".env"
    content = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    values = dotenv_values(path) if path.exists() else {}
    defaults = {
        "NEO4J_URI": "bolt://127.0.0.1:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": secrets.token_urlsafe(24),
        "NEO4J_DATABASE": "neo4j",
        "GRAPH_BACKEND": "neo4j",
    }
    for key, value in defaults.items():
        existing = values.get(key)
        if existing and existing != "CHANGE_ME_BEFORE_START":
            continue
        pattern = rf"(?m)^{key}=.*$"
        if re.search(pattern, content):
            content = re.sub(pattern, f"{key}={value}", content)
        else:
            content = content.rstrip() + f"\n{key}={value}\n"
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    prepare_environment()
    print("Neo4j local configured; credentials remain in .env; RAG flags unchanged.")
