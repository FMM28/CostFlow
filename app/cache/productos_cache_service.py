from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from flask import current_app

from app.cache.redis_cache import RedisCache
from app.cache.redis_keys import RedisKeys
from app.models.producto_proveedor import ProductoProveedor, ExistenciaSucursal


class ProductosCacheService:
    def __init__(self):
        self.cache = RedisCache()

    @property
    def ttl(self) -> int:
        return current_app.config["PRODUCTOS_CACHE_TTL"]

    def get(self, sku: str) -> Optional[dict[str, ProductoProveedor]]:
        """
        Retorna productos por proveedor si el caché es válido.
        """
        key = RedisKeys.producto(sku)

        raw = self.cache.get_json(key)
        if not raw:
            return None

        if self._is_expired(raw):
            self.cache.delete(key)
            return None

        return self._deserialize(raw["data"])

    def set(
        self,
        sku: str,
        productos: list[ProductoProveedor],
    ) -> None:
        """
        Guarda lista de productos agrupados por proveedor.
        """

        key = RedisKeys.producto(sku)

        grouped = self._group_by_provider(productos)

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": grouped,
        }

        self.cache.set_json(key, payload, ttl=self.ttl)

    def update_provider(
        self,
        sku: str,
        producto: ProductoProveedor,
    ) -> None:
        """
        Actualiza solo un proveedor dentro del SKU.
        """

        current = self.get_raw(sku)

        if current is None:
            current = {}

        current["data"][producto.proveedor] = self._serialize_product(producto)

        self.cache.set_json(
            RedisKeys.producto(sku),
            current,
            ttl=self.ttl,
        )

    def delete(self, sku: str) -> None:
        self.cache.delete(RedisKeys.producto(sku))

    def get_raw(self, sku: str) -> Optional[dict]:
        return self.cache.get_json(RedisKeys.producto(sku))

    def _is_expired(self, raw: dict) -> bool:
        """
        Expiración lógica adicional (defensa en profundidad).
        Redis ya expira, pero esto protege contra inconsistencias.
        """
        timestamp = raw.get("timestamp")
        if not timestamp:
            return True

        try:
            dt = datetime.fromisoformat(timestamp)
        except ValueError:
            return True

        now = datetime.now(timezone.utc)
        age = (now - dt).total_seconds()

        return age > self.ttl

    def _group_by_provider(
        self,
        productos: list[ProductoProveedor],
    ) -> dict:
        grouped = {}

        for p in productos:
            grouped[p.proveedor] = self._serialize_product(p)

        return grouped

    def _serialize_product(self, p: ProductoProveedor) -> dict:
        return {
            "proveedor": p.proveedor,
            "nombre": p.nombre,
            "precio": str(p.precio),
            "moneda": p.moneda,
            "existencia": p.existencia,
            "descuento": str(p.descuento) if p.descuento else None,
            "existencias_sucursal": [
                {
                    "sucursal": e.sucursal,
                    "existencia": e.existencia,
                }
                for e in (p.existencias_sucursal or [])
            ],
            "url": p.url,
            "url_imagen": p.url_imagen,
        }

    def _deserialize(
        self,
        data: dict,
    ) -> dict[str, ProductoProveedor]:

        result = {}

        for proveedor, p in data.items():
            result[proveedor] = ProductoProveedor(
                proveedor=p["proveedor"],
                nombre=p["nombre"],
                precio=Decimal(p["precio"]),
                moneda=p["moneda"],
                existencia=p["existencia"],
                descuento=Decimal(p["descuento"]) if p.get("descuento") else None,
                existencias_sucursal=[
                    ExistenciaSucursal(
                        sucursal=e["sucursal"],
                        existencia=e["existencia"],
                    )
                    for e in (p.get("existencias_sucursal") or [])
                ],
                url=p.get("url"),
                url_imagen=p.get("url_imagen"),
            )

        return result
