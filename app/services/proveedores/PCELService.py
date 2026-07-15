import logging
import re
from decimal import Decimal
from urllib.parse import urljoin

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException
from bs4 import BeautifulSoup

from app.models.producto_proveedor import ProductoProveedor, ExistenciaSucursal
from app.services.proveedores.proveedor_productos import ProveedorProductos

logger = logging.getLogger(__name__)


class PCELService(ProveedorProductos):
    PROVEEDOR = "PCEL"

    def __init__(self):
        self.BASE_URL = "https://www.pcel.com"
        self.BUSCADOR_URL = f"{self.BASE_URL}/search"

    @classmethod
    def _get_instance(cls):
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _get_session(cls):
        if not hasattr(cls, "_session"):
            cls._session = requests.Session(impersonate="chrome120")

            cls._session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                    "Accept-Language": "es-419,es;q=0.7,en;q=0.3",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Cache-Control": "max-age=0",
                    "DNT": "1",
                }
            )

        return cls._session

    @staticmethod
    def _parse_precio(texto):
        if not texto:
            return None

        match = re.search(r"\$([\d,]+)(?:\.(\d{2}))?", texto)
        if not match:
            return None

        entero = match.group(1).replace(",", "")
        decimales = match.group(2) or "00"

        return Decimal(f"{entero}.{decimales}")

    @classmethod
    def buscar_producto(cls, nombre=None, sku=None):
        termino = sku or nombre
        if not termino:
            return None

        try:
            ins = cls._get_instance()
            session = cls._get_session()

            response = session.get(
                ins.BUSCADOR_URL,
                params={"q": termino},
                allow_redirects=True,
                timeout=20,
            )
            response.raise_for_status()

            if "/search" in str(response.url):
                logger.info("PCEL: producto '%s' no encontrado.", termino)
                return None

            html = response.text
            return cls._parse_producto(html, response.url)

        except RequestException:
            logger.exception("Error consultando PCEL para '%s'.", termino)
            raise
        except Exception:
            logger.exception("Error procesando respuesta de PCEL para '%s'.", termino)
            raise

    @classmethod
    def _parse_producto(cls, html, url):
        soup = BeautifulSoup(html, "html.parser")

        nombre = None
        precio = None
        precio_original = None
        imagen = None
        existencia_total = 0
        existencias_sucursal = []

        try:
            nombre_div = soup.select_one("div.pdp_banner_title h3")
            if nombre_div:
                nombre = " ".join(nombre_div.get_text(" ", strip=True).split())
        except Exception:
            logger.exception("Error obteniendo nombre del producto.")

        try:
            precio_div = soup.select_one("div.vatprice_top")
            if precio_div:
                strong = precio_div.select_one("strong")
                if strong:
                    precio = cls._parse_precio(strong.get_text())

                anterior = precio_div.select_one("s")
                if anterior:
                    precio_original = cls._parse_precio(anterior.get_text())

            if precio_original is None:
                precio_original = precio
                precio = None

        except Exception:
            logger.exception("Error obteniendo precios del producto.")

        try:
            stock_div = soup.select_one("div.vat_stock")
            if stock_div:
                tabla = stock_div.select_one("table")
                if tabla:
                    sucursales = [
                        th.get_text(" ", strip=True) for th in tabla.select("thead th")
                    ]

                    cantidades = [
                        td.get_text(" ", strip=True)
                        for td in tabla.select("tbody tr td")
                    ]

                    for sucursal, texto in zip(sucursales, cantidades):
                        match = re.search(r"\d+", texto)
                        if not match:
                            continue

                        cantidad = int(match.group())

                        existencias_sucursal.append(
                            ExistenciaSucursal(
                                sucursal=sucursal,
                                existencia=cantidad,
                            )
                        )

                        existencia_total += cantidad

        except Exception:
            logger.exception("Error obteniendo existencias del producto.")

        try:
            imagen_tag = soup.select_one('meta[property="og:image"]')
            if imagen_tag:
                imagen = urljoin(url, imagen_tag.get("content"))
        except Exception:
            logger.exception("Error obteniendo imagen del producto.")

        if nombre is None:
            logger.warning(
                "PCEL: no fue posible obtener el nombre del producto (%s).", url
            )
            return None

        if precio_original is None:
            logger.warning("PCEL: no fue posible obtener el precio de '%s'.", nombre)
            return None

        return ProductoProveedor(
            proveedor=cls.PROVEEDOR,
            nombre=nombre,
            precio=precio_original,
            moneda="MXN",
            existencia=existencia_total,
            descuento=precio,
            existencias_sucursal=existencias_sucursal,
            url=url,
            url_imagen=imagen,
        )
