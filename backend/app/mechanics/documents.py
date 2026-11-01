"""Mechanics' ID documents, encrypted at rest with MECHANIC_DOCS_KEY (Fernet: AES-128-CBC + HMAC). The key is never
derived from another secret: without it, uploads are refused (DocumentsKeyMissing)."""

from cryptography.fernet import Fernet, InvalidToken

from app.admin.security import PLACEHOLDERS
from app.config import Settings

ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MAGIC = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


class DocumentsKeyMissing(RuntimeError):
    pass


class DocumentUnreadable(RuntimeError):
    """The stored ciphertext doesn't open with the current key (the key was changed or lost)."""


def _fernet(settings: Settings) -> Fernet:
    key = settings.mechanic_docs_key.strip()
    if key in PLACEHOLDERS:
        raise DocumentsKeyMissing("MECHANIC_DOCS_KEY is not set: documents can't be stored")
    try:
        return Fernet(key)
    except ValueError as e:
        raise DocumentsKeyMissing("MECHANIC_DOCS_KEY is not a valid Fernet key") from e


def sniff(content: bytes) -> str | None:
    """The file's real type from its first bytes (the browser's content type is not trusted)."""
    for kind, prefixes in MAGIC.items():
        if any(content.startswith(p) for p in prefixes):
            if kind == "image/webp" and content[8:12] != b"WEBP":
                continue
            return kind
    return None


def encrypt(settings: Settings, content: bytes) -> bytes:
    return _fernet(settings).encrypt(content)


def decrypt(settings: Settings, ciphertext: bytes) -> bytes:
    try:
        return _fernet(settings).decrypt(ciphertext)
    except InvalidToken as e:
        raise DocumentUnreadable("this document can't be opened with the current MECHANIC_DOCS_KEY") from e
