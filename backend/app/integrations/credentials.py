"""Read API credentials and atomically save keys supplied through settings."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
from ..core.settings import settings


def gigachat_key() -> str:
    path = Path(settings.gigachat_key_path)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return settings.gigachat_key.strip()


def embedding_key() -> str:
    path = Path(settings.embedding_key_path)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return settings.embedding_api_key.strip()


def save_gigachat_key(value: str):
    save_key(settings.gigachat_key_path, value, ".gigachat-")


def save_embedding_key(value: str):
    save_key(settings.embedding_key_path, value, ".embedding-")


def save_key(filename: str, value: str, prefix: str):
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=prefix, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(value.strip())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
