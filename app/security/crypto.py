"""Cryptographic secret protection at rest for DADUS.
Uses native Windows DPAPI (CryptProtectData / CryptUnprotectData) on Windows hosts,
with a machine-local keyed fallback for Linux/Docker environments.
"""
import os
import hmac
import hashlib
import base64
import secrets
import logging
from pathlib import Path
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger("DADUS.Crypto")

_DPAPI_PREFIX = "dpapi:"
_LOCAL_PREFIX = "local:"


def _dpapi_protect(raw_bytes: bytes) -> Optional[bytes]:
    """Encrypt bytes using native Windows DPAPI tied to the current Windows user."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        in_buf = ctypes.create_string_buffer(raw_bytes, len(raw_bytes))
        in_blob = DATA_BLOB(len(raw_bytes), in_buf)
        out_blob = DATA_BLOB()

        # CRYPTPROTECT_UI_FORBIDDEN = 0x1
        if not crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            "DADUS_SECRET",
            None,
            None,
            None,
            0x1,
            ctypes.byref(out_blob),
        ):
            return None

        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception as ex:
        logger.debug(f"DPAPI protect unavailable: {ex}")
        return None


def _dpapi_unprotect(cipher_bytes: bytes) -> Optional[bytes]:
    """Decrypt Windows DPAPI protected bytes."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        in_buf = ctypes.create_string_buffer(cipher_bytes, len(cipher_bytes))
        in_blob = DATA_BLOB(len(cipher_bytes), in_buf)
        out_blob = DATA_BLOB()

        if not crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            0x1,
            ctypes.byref(out_blob),
        ):
            return None

        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception as ex:
        logger.debug(f"DPAPI unprotect failed: {ex}")
        return None


def _get_or_create_local_key() -> bytes:
    """Get or generate a 32-byte machine-local key for non-Windows environments."""
    key_path: Path = settings.DATA_DIR / ".secret_key"
    if key_path.exists():
        raw = key_path.read_bytes().strip()
        if len(raw) >= 32:
            return hashlib.sha256(raw).digest()
    key_bytes = secrets.token_bytes(32)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(base64.urlsafe_b64encode(key_bytes))
    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass
    return hashlib.sha256(base64.urlsafe_b64encode(key_bytes)).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Derive deterministic CTR-style keystream via SHA-256."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    """Encrypts a sensitive string at rest. Returns self-describing prefixed ciphertext."""
    if not plaintext:
        return plaintext
    raw = plaintext.encode("utf-8")

    # Prefer native OS DPAPI on Windows
    dpapi_blob = _dpapi_protect(raw)
    if dpapi_blob is not None:
        return _DPAPI_PREFIX + base64.urlsafe_b64encode(dpapi_blob).decode("ascii")

    # Portable authenticated stream cipher fallback (Linux/Docker)
    key = _get_or_create_local_key()
    nonce = secrets.token_bytes(16)
    stream = _keystream(key, nonce, len(raw))
    cipher = bytes(a ^ b for a, b in zip(raw, stream))
    mac = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    payload = nonce + mac + cipher
    return _LOCAL_PREFIX + base64.urlsafe_b64encode(payload).decode("ascii")


def decrypt_secret(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypts a secret encrypted by `encrypt_secret`. Handles legacy plaintext gracefully."""
    if not ciphertext:
        return ciphertext

    if ciphertext.startswith(_DPAPI_PREFIX):
        blob = base64.urlsafe_b64decode(ciphertext[len(_DPAPI_PREFIX):].encode("ascii"))
        plain = _dpapi_unprotect(blob)
        if plain is None:
            raise ValueError("Unable to decrypt DPAPI-protected secret on this host/user.")
        return plain.decode("utf-8")

    if ciphertext.startswith(_LOCAL_PREFIX):
        payload = base64.urlsafe_b64decode(ciphertext[len(_LOCAL_PREFIX):].encode("ascii"))
        if len(payload) < 48:
            raise ValueError("Corrupted local encrypted secret payload.")
        nonce, mac, cipher = payload[:16], payload[16:48], payload[48:]
        key = _get_or_create_local_key()
        expected_mac = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("Encrypted secret authentication tag mismatch.")
        stream = _keystream(key, nonce, len(cipher))
        raw = bytes(a ^ b for a, b in zip(cipher, stream))
        return raw.decode("utf-8")

    # Legacy unprefixed value
    return ciphertext
