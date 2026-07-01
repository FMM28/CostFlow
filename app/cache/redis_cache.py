from __future__ import annotations

import json
from typing import Any

from redis.exceptions import RedisError

from app.extensions import get_redis


class RedisCache:
    """Wrapper para operaciones comunes sobre Redis."""
    
    def __init__(self):
        self.redis_client = get_redis()

    def get(self, key: str) -> str | None:
        try:
            return self.redis_client.get(key)
        except RedisError:
            return None

    def get_json(self, key: str) -> dict[str, Any] | list[Any] | None:
        value = self.get(key)

        if value is None:
            return None

        return json.loads(value)

    def set(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
    ) -> bool:
        try:
            return bool(self.redis_client.set(key, value, ex=ttl))
        except RedisError:
            return False

    def set_json(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        ttl: int | None = None,
    ) -> bool:
        return self.set(
            key=key,
            value=json.dumps(value, separators=(",", ":")),
            ttl=ttl,
        )

    def delete(self, key: str) -> bool:
        try:
            return self.redis_client.delete(key) > 0
        except RedisError:
            return False

    def exists(self, key: str) -> bool:
        try:
            return bool(self.redis_client.exists(key))
        except RedisError:
            return False

    def expire(self, key: str, ttl: int) -> bool:
        try:
            return bool(self.redis_client.expire(key, ttl))
        except RedisError:
            return False

    def ttl(self, key: str) -> int:
        try:
            return self.redis_client.ttl(key)
        except RedisError:
            return -2

    def keys(self, pattern: str) -> list[str]:
        try:
            return self.redis_client.keys(pattern)
        except RedisError:
            return []

    def clear_pattern(self, pattern: str) -> int:
        """
        Elimina todas las claves que coincidan con el patrón.
        Retorna la cantidad de claves eliminadas.
        """
        try:
            keys = self.redis_client.keys(pattern)

            if not keys:
                return 0

            return self.redis_client.delete(*keys)
        except RedisError:
            return 0

    def ping(self) -> bool:
        try:
            return bool(self.redis_client.ping())
        except RedisError:
            return False
