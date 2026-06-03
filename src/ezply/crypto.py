import json
import os
import base64

from typing import Tuple

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
        backend=default_backend(),
    )
    key = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def encrypt_json(obj: dict, passphrase: str) -> Tuple[bytes, bytes]:
    """Return (salt, ciphertext)"""
    salt = os.urandom(16)
    key = _derive_key(passphrase, salt)
    f = Fernet(key)
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    token = f.encrypt(payload)
    return salt, token


def decrypt_json(salt: bytes, token: bytes, passphrase: str) -> dict:
    key = _derive_key(passphrase, salt)
    f = Fernet(key)
    plaintext = f.decrypt(token)
    return json.loads(plaintext.decode("utf-8"))
