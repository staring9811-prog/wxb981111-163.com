"""密码哈希与密钥加密（NFR-008：密钥只以加密形式保存在本机）。"""
import os
import secrets as _secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet

from .config import data_dir

_ph = PasswordHasher()


def hash_pw(pw: str) -> str:
    return _ph.hash(pw)


def check_pw(h: str, pw: str) -> bool:
    try:
        return _ph.verify(h, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def new_token() -> str:
    return _secrets.token_urlsafe(32)


def _fernet() -> Fernet:
    p = data_dir() / "secret.key"
    if not p.exists():
        p.write_bytes(Fernet.generate_key())
        os.chmod(p, 0o600)
    return Fernet(p.read_bytes())


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt(blob: bytes) -> str:
    return _fernet().decrypt(blob).decode()


def mask(value: str) -> str:
    return value[-4:] if len(value) >= 4 else value
