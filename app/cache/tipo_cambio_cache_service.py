from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from flask import current_app

from app.cache.redis_cache import RedisCache
from app.cache.redis_keys import RedisKeys


@dataclass(slots=True)
class TipoCambioCache:
    moneda: str
    valor: Decimal


class TipoCambioCacheService:
    def __init__(self):
        self.cache = RedisCache()

    @property
    def ttl(self) -> int:
        return current_app.config["TIPO_CAMBIO_CACHE_TTL"]

    def obtener(
        self,
        moneda: str,
    ) -> Optional[TipoCambioCache]:

        data = self.cache.get_json(RedisKeys.tipo_cambio(moneda))

        if data is None:
            return None

        return TipoCambioCache(
            moneda=data["moneda"],
            valor=Decimal(data["valor"]),
        )

    def guardar(
        self,
        tipo_cambio: TipoCambioCache,
    ) -> None:

        payload = {
            "moneda": tipo_cambio.moneda.upper(),
            "valor": str(tipo_cambio.valor),
        }

        self.cache.set_json(
            RedisKeys.tipo_cambio(tipo_cambio.moneda),
            payload,
            ttl=self.ttl,
        )

    def eliminar(
        self,
        moneda: str,
    ) -> None:

        self.cache.delete(RedisKeys.tipo_cambio(moneda))

    def existe(
        self,
        moneda: str,
    ) -> bool:

        return self.cache.exists(RedisKeys.tipo_cambio(moneda))

    def ttl_restante(
        self,
        moneda: str,
    ) -> int:

        return self.cache.ttl(RedisKeys.tipo_cambio(moneda))
