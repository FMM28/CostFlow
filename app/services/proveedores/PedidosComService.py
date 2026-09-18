
import requests
from flask import current_app

from app.models.producto_proveedor import ProductoProveedor
from app.services.proveedores.proveedor_productos import ProveedorProductos


class PedidosComService(ProveedorProductos):
    PROVEEDOR = "PEDIDOS_COM"

    ALGOLIA_INDEX = "Pedidos"
    ALGOLIA_URL = "https://12ythfxxb5-dsn.algolia.net/1/indexes/*/queries"

    @classmethod
    def buscar_producto(cls, nombre=None, sku=None):
        termino = sku or nombre

        if not termino:
            return None

        app_id = current_app.config.get("PEDIDOS_COM_ALGOLIA_APP_ID")
        api_key = current_app.config.get("PEDIDOS_COM_ALGOLIA_API_KEY")

        if not app_id or not api_key:
            return None

        headers = {
            "X-Algolia-Application-Id": app_id,
            "X-Algolia-API-Key": api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "requests": [
                {
                    "indexName": cls.ALGOLIA_INDEX,
                    "query": termino,
                }
            ]
        }

        response = requests.post(
            cls.ALGOLIA_URL,
            headers=headers,
            json=payload,
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        if not results:
            return None

        hits = results[0].get("hits", [])

        if not hits:
            return None

        hit = cls._obtener_hit(hits, sku)

        if not hit:
            return None

        return cls._crear_producto(hit)

    @classmethod
    def _obtener_hit(cls, hits, sku=None):
        if sku:
            sku_normalizado = str(sku).strip().upper()

            for hit in hits:
                filtros = hit.get("FILTROS") or {}

                articulo = str(
                    filtros.get("ARTÍCULO", "")
                ).strip().upper()

                sort_name = str(
                    hit.get("SORT_NAME", "")
                ).strip().upper()

                if (
                    articulo == sku_normalizado
                    or sort_name == sku_normalizado
                ):
                    return hit

        return hits[0] if hits else None

    @classmethod
    def _crear_producto(cls, hit):
        url = hit.get("URL")

        if url:
            url = f"https://www.pedidos.com/articulos/{url.lstrip('/')}"

        return ProductoProveedor(
            proveedor=cls.PROVEEDOR,
            nombre=hit.get("TITULO"),
            precio=hit.get("PRECIO"),
            moneda="MXN",
            existencia=hit.get("STOCK"),
            descuento=None,
            existencias_sucursal=None,
            url=url,
            url_imagen=None,
        )