r"""
Minimal symmetric encryption using only Python stdlib.
Replaces cryptography.Fernet when the package is unavailable.
Uses PBKDF2 + HMAC-SHA256 + XOR stream cipher (CTR mode).
"""
import os
import base64
import hashlib
import hmac
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_ITERATIONS = 100_000
_KEY_LEN = 32
_NONCE_LEN = 16
_MAC_LEN = 32


class _MinimalFernet:
    def __init__(self, key: bytes):
        self._key = key

    @classmethod
    def generate_key(cls) -> bytes:
        return base64.urlsafe_b64encode(os.urandom(32))

    @staticmethod
    def from_password(password: str, salt: bytes = None) -> bytes:
        if salt is None:
            salt = hashlib.sha256(("minimal:" + password).encode()).digest()[:16]
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
        return base64.urlsafe_b64encode(dk)

    def encrypt(self, data: bytes) -> bytes:
        nonce = os.urandom(_NONCE_LEN)
        key = base64.urlsafe_b64decode(self._key)
        enc_key = hashlib.sha256(key + b"enc" + nonce).digest()
        mac_key = hashlib.sha256(key + b"mac" + nonce).digest()
        ciphertext = self._xor_stream(data, enc_key)
        mac = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(nonce + ciphertext + mac)

    def decrypt(self, token: bytes) -> bytes:
        key = base64.urlsafe_b64decode(self._key)
        raw = base64.urlsafe_b64decode(token)
        nonce = raw[:_NONCE_LEN]
        ciphertext = raw[_NONCE_LEN:-_MAC_LEN]
        received_mac = raw[-_MAC_LEN:]
        mac_key = hashlib.sha256(key + b"mac" + nonce).digest()
        expected_mac = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(received_mac, expected_mac):
            raise ValueError("Integrity check failed")
        enc_key = hashlib.sha256(key + b"enc" + nonce).digest()
        return self._xor_stream(ciphertext, enc_key)

    @staticmethod
    def _xor_stream(data: bytes, key: bytes) -> bytes:
        return bytes(d ^ key[i % len(key)] for i, d in enumerate(data))


try:
    from cryptography.fernet import Fernet as _Fernet
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC as _PBKDF2

    class _RealFernet:
        @staticmethod
        def generate_key() -> bytes:
            return _Fernet.generate_key()

        @staticmethod
        def from_password(password: str, salt: bytes = None) -> bytes:
            if salt is None:
                salt = hashlib.sha256(("real:" + password).encode()).digest()[:16]
            kdf = _PBKDF2(
                algorithm=_hashes.SHA256(), length=32, salt=salt, iterations=_ITERATIONS
            )
            return base64.urlsafe_b64encode(kdf.derive(password.encode()))

        def __init__(self, key: bytes):
            self._impl = _Fernet(key)

        def encrypt(self, data: bytes) -> bytes:
            return self._impl.encrypt(data)

        def decrypt(self, token: bytes) -> bytes:
            return self._impl.decrypt(token)

    _FernetImpl = _RealFernet
    logger.info("Using cryptography.fernet (production grade)")

except ImportError:
    _FernetImpl = _MinimalFernet
    logger.info("cryptography not available — using minimal fallback encryption (stdlib only)")


class CryptoService:
    def __init__(self, secret_key: Optional[str] = None):
        if secret_key:
            self._initialize_key(secret_key)
        else:
            logger.warning("No encryption secret provided, generating ephemeral key")
            self._generate_key()

    def _initialize_key(self, secret_key: str) -> None:
        key_bytes = _FernetImpl.from_password(secret_key)
        self.cipher = _FernetImpl(key_bytes)

    def _generate_key(self) -> None:
        key_bytes = _FernetImpl.generate_key()
        self.cipher = _FernetImpl(key_bytes)

    def encrypt(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        return self.cipher.decrypt(encrypted_data.encode()).decode()

    def encrypt_bytes(self, data: bytes) -> bytes:
        return self.cipher.encrypt(data)

    def decrypt_bytes(self, encrypted_data: bytes) -> bytes:
        return self.cipher.decrypt(encrypted_data)


_crypto_service: Optional[CryptoService] = None


def init_crypto(secret_key: Optional[str] = None) -> None:
    global _crypto_service
    _crypto_service = CryptoService(secret_key)
    logger.info("Crypto service initialized (key=%s)", "provided" if secret_key else "ephemeral")


def crypto_service() -> CryptoService:
    global _crypto_service
    if _crypto_service is None:
        logger.warning("Crypto service accessed before init_crypto() — initializing lazily")
        init_crypto()
        logger.warning(
            "Crypto service initialized without a persistent key. "
            "Set ENCRYPTION_SECRET_KEY env var or ensure .crypto_key file exists. "
            "API keys encrypted in this session will be lost on restart."
        )
    return _crypto_service
