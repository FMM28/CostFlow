from __future__ import annotations

import base64
import logging
import os

from flask import current_app

from .key_provider import KeyProvider

logger = logging.getLogger(__name__)

_MIN_KEY_BYTES = 32  # 256 bits mínimo de entropía


class KeyProviderError(Exception):
    """Se lanza cuando la master key no está configurada o es inválida."""


class EnvKeyProvider(KeyProvider):
    _CONFIG_KEY = "MASTER_ENCRYPTION_KEY"

    _cached_key: bytes | None = None

    def get_master_key(self) -> bytes:
        if self._cached_key is not None:
            return self._cached_key

        raw_value = self._read_raw_value()
        key_bytes = self._decode(raw_value)
        self._validate(key_bytes)

        self._cached_key = key_bytes
        return key_bytes

    def _read_raw_value(self) -> str:
        value = None

        if current_app:
            value = current_app.config.get(self._CONFIG_KEY)

        if not value:
            value = os.environ.get(self._CONFIG_KEY)

        if not value:
            logger.exception(
                "%s no está configurada (ni en app.config ni en el entorno)",
                self._CONFIG_KEY,
            )
            raise KeyProviderError(f"{self._CONFIG_KEY} no está configurada")

        return value

    def _decode(self, raw_value: str) -> bytes:
        padding_needed = (-len(raw_value)) % 4
        padded_value = raw_value + ("=" * padding_needed)

        try:
            key_bytes = base64.urlsafe_b64decode(padded_value)
        except (ValueError, TypeError) as exc:
            logger.exception(
                "%s no tiene un formato base64 url-safe válido", self._CONFIG_KEY
            )
            raise KeyProviderError(
                f"{self._CONFIG_KEY} debe estar codificada en base64 url-safe"
            ) from exc

        return key_bytes

    def _validate(self, key_bytes: bytes) -> None:
        if len(key_bytes) < _MIN_KEY_BYTES:
            logger.exception(
                "%s tiene solo %d bytes, se requieren al menos %d",
                self._CONFIG_KEY,
                len(key_bytes),
                _MIN_KEY_BYTES,
            )
            raise KeyProviderError(
                f"{self._CONFIG_KEY} debe tener al menos {_MIN_KEY_BYTES} bytes"
            )
