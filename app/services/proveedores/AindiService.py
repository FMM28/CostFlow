import logging
from decimal import Decimal

import requests
import re
import unicodedata

from app.models.producto_proveedor import ProductoProveedor
from app.services.proveedores.proveedor_productos import ProveedorProductos

logger = logging.getLogger(__name__)


class AindiService(ProveedorProductos):
    PROVEEDOR = "AINDI"

    ALGOLIA_URL = "https://6dei1e1pew-dsn.algolia.net/1/indexes/produccion/query"

    def __init__(self):
        self.session = self._get_session()

    @classmethod
    def _get_instance(cls):
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _get_session(cls):
        if not hasattr(cls, "_session"):
            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/137.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "x-algolia-agent": (
                        "Algolia for JavaScript (5.40.0); Search (5.40.0); Browser"
                    ),
                    "x-algolia-api-key": "2f1a38e77be7bc94e8aefebdc897dabd",
                    "x-algolia-application-id": "6DEI1E1PEW",
                }
            )
            cls._session = session

        return cls._session

    @classmethod
    def buscar_producto(cls, nombre=None, sku=None):
        termino = (sku or nombre or "").strip()
        if not termino:
            return None

        try:
            hit = cls._buscar_algolia(termino)
            if hit is None:
                logger.info("AINDI: Producto '%s' no encontrado.", termino)
                return None

            return cls._crear_producto(hit)

        except requests.RequestException:
            logger.exception("Error consultando AINDI para '%s'.", termino)
            return None
        except Exception:
            logger.exception("Error procesando respuesta de AINDI para '%s'.", termino)
            return None

    @classmethod
    def _buscar_algolia(cls, sku):
        session = cls._get_session()

        response = session.post(
            cls.ALGOLIA_URL,
            json={"query": sku},
            timeout=15,
        )
        response.raise_for_status()

        data = response.json()

        for hit in data.get("hits", []):
            if (
                hit.get("productKey", "").upper() == sku.upper()
                and hit.get("status") == "activo"
            ):
                return hit

        return None

    @classmethod
    def _crear_producto(cls, hit):
        precio = hit.get("price_user")

        if precio in ("", None):
            logger.warning(
                "AINDI: El producto '%s' no tiene precio.",
                hit.get("productKey"),
            )
            return None

        try:
            precio = Decimal(str(precio))
        except Exception:
            logger.exception(
                "AINDI: No fue posible convertir el precio '%s'.",
                precio,
            )
            return None

        try:
            existencia = int(hit.get("quantity", 0))
        except Exception:
            existencia = 0

        imagen = None
        pictures = hit.get("pictures") or []
        if pictures:
            imagen = pictures[0]

        return ProductoProveedor(
            proveedor=cls.PROVEEDOR,
            nombre=hit.get("title"),
            precio=precio,
            moneda="MXN",
            existencia=existencia,
            descuento=0,
            existencias_sucursal=None,
            url=(
                "https://aindi.mx/productos/"
                f"{cls._slugify(hit['nameCategoria'])}/"
                f"{cls._slugify(hit['nameSubcategoria'])}/"
                f"{hit['slug']}?id={hit['id']}"
            ),
            url_imagen=imagen,
        )

    @classmethod
    def _slugify(cls,texto):
        texto = unicodedata.normalize("NFKD", texto)
        texto = texto.encode("ascii", "ignore").decode("ascii")
        texto = texto.lower()
        texto = re.sub(r"[^a-z0-9]+", "-", texto)
        return texto.strip("-")
