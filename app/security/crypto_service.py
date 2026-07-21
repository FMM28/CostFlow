from __future__ import annotations

import base64
import hashlib
import json
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from .env_key_provider import EnvKeyProvider

logger = logging.getLogger(__name__)


class DecryptionError(Exception):
    """Se lanza cuando un valor cifrado no puede ser descifrado o verificado."""


class CryptoService:
    _provider = EnvKeyProvider()

    _PURPOSE_CREDENTIALS = b"credentials"
    _PURPOSE_SESSIONS = b"sessions"

    # Versión de clave activa para cifrar. Al rotar la master key, incrementar
    # esto y agregar la anterior a _LEGACY_MASTER_KEYS para poder seguir
    # descifrando valores viejos.
    _KEY_VERSION = "v1"

    # Master keys anteriores, solo para descifrar. Ejemplo:
    # {"v1": b"<master key anterior>"}
    _LEGACY_MASTER_KEYS: dict[str, bytes] = {}

    @classmethod
    def encrypt_credentials(cls, value: dict | list | str) -> str:
        return cls._encrypt(value, cls._PURPOSE_CREDENTIALS)

    @classmethod
    def decrypt_credentials(cls, value: str):
        return cls._decrypt(value, cls._PURPOSE_CREDENTIALS)

    @classmethod
    def encrypt_session(cls, value: dict | list) -> str:
        return cls._encrypt(value, cls._PURPOSE_SESSIONS)

    @classmethod
    def decrypt_session(cls, value: str):
        return cls._decrypt(value, cls._PURPOSE_SESSIONS)

    @classmethod
    def _encrypt(cls, value, purpose: bytes) -> str:

        if isinstance(value, (dict, list)):
            plaintext = json.dumps(value, separators=(",", ":")).encode()
        elif isinstance(value, str):
            plaintext = value.encode()
        else:
            logger.exception(
                "Tipo no soportado al cifrar (purpose=%s): %s",
                purpose.decode(),
                type(value).__name__,
            )
            raise TypeError("Tipo no soportado")

        try:
            fernet = Fernet(cls._derive_key(cls._current_master_key(), purpose))
            token = fernet.encrypt(plaintext).decode()
        except Exception:
            logger.exception(
                "Error inesperado al cifrar un valor (purpose=%s)", purpose.decode()
            )
            raise

        return f"{cls._KEY_VERSION}:{token}"

    @classmethod
    def _decrypt(cls, value: str, purpose: bytes):

        version, sep, token = value.partition(":")

        if not sep:
            logger.exception(
                "Formato de valor cifrado inválido (purpose=%s): falta el prefijo de versión",
                purpose.decode(),
            )
            raise DecryptionError("Formato de valor cifrado inválido")

        master_key = cls._master_key_for_version(version, purpose)
        fernet = Fernet(cls._derive_key(master_key, purpose))

        try:
            plaintext = fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            logger.exception(
                "Token inválido o corrupto al descifrar (purpose=%s, version=%s)",
                purpose.decode(),
                version,
            )
            raise DecryptionError(
                "No se pudo descifrar el valor: token inválido, corrupto o clave incorrecta"
            ) from exc

        try:
            return json.loads(plaintext)
        except json.JSONDecodeError:
            return plaintext

    @classmethod
    def _current_master_key(cls) -> bytes:
        return cls._provider.get_master_key()

    @classmethod
    def _master_key_for_version(cls, version: str, purpose: bytes) -> bytes:
        if version == cls._KEY_VERSION:
            return cls._current_master_key()
        try:
            return cls._LEGACY_MASTER_KEYS[version]
        except KeyError as exc:
            logger.exception(
                "No se encontró master key para la versión '%s' (purpose=%s)",
                version,
                purpose.decode(),
            )
            raise DecryptionError(
                f"No se conoce ninguna master key para la versión '{version}'"
            ) from exc

    @classmethod
    @lru_cache(maxsize=None)
    def _derive_key(cls, master_key: bytes, purpose: bytes) -> bytes:

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=hashlib.sha256(b"CostFlow").digest(),
            info=purpose,
        )

        derived_key = hkdf.derive(master_key)

        return base64.urlsafe_b64encode(derived_key)
