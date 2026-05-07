import base64
import hashlib

from cryptography.fernet import Fernet


def _make_fernet(secret_key: str) -> Fernet:
    key_bytes = hashlib.sha256(secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt(value: str, secret_key: str) -> str:
    return _make_fernet(secret_key).encrypt(value.encode()).decode()


def decrypt(value: str, secret_key: str) -> str:
    return _make_fernet(secret_key).decrypt(value.encode()).decode()
