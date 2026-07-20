import logging
import re
from decimal import Decimal

import requests
from bs4 import BeautifulSoup
from flask import current_app

from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.models.producto_proveedor import (
    ExistenciaSucursal,
    ProductoProveedor,
)
from app.services.sesion_proveedor_service import SesionProveedorService

logger = logging.getLogger(__name__)


class TechSmartService(ProveedorProductos):
    PROVEEDOR = "TECHSMART"

    def __init__(self):
        base_url = self._get_base_url()
        self.CLIENTES_URL = f"{base_url}/Clientes/"
        self.CATALOGO_URL = f"{base_url}/Clientes/Catalogo"
        self.EXISTENCIAS_URL = f"{base_url}/Clientes/acciones/cargaExistencias.php"
        self.LOGIN_URL = f"{base_url}/acciones/login.php"
        self.BASE_URL = base_url

    @classmethod
    def _get_base_url(cls) -> str:
        """Obtiene la URL base desde la configuración de la aplicación."""
        try:
            return current_app.config["TECHSMART_URL"]
        except (RuntimeError, KeyError) as e:
            logger.error(f"Error obteniendo TECHSMART_URL: {e}")
            raise ValueError("La URL de SYSCOM no está configurada (SYSCOM_URL)")

    @classmethod
    def _get_instance(cls):
        """Obtiene una instancia de la clase para acceder a las URLs."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    @classmethod
    def buscar_producto(
        cls,
        nombre: str | None = None,
        sku: str | None = None,
    ) -> ProductoProveedor | None:

        termino = sku or nombre

        if not termino:
            return None

        cookies = cls._obtener_cookies_validas()

        if not cookies:
            return None

        instance = cls._get_instance()

        params = {
            "txtCategoria": "-1",
            "EnPromo": "T",
            "txtBuscar": termino,
            "marcasFilter": "",
            "mayorPrecio": "",
            "PreciosTodos": "",
        }

        try:
            response = requests.get(
                instance.CATALOGO_URL,
                params=params,
                cookies=cookies,
                timeout=15,
            )

            response.raise_for_status()

            return cls._parsear_catalogo(
                response.text,
                cookies,
                sku,
                instance.BASE_URL,
            )

        except Exception:
            logger.exception("Error consultando TechSmart.")
            return None

    @classmethod
    def _obtener_cookies_validas(cls) -> dict:

        cookies = SesionProveedorService.obtener(cls.PROVEEDOR)

        if cookies:
            if cls._sesion_activa(cookies):
                return cookies

            SesionProveedorService.eliminar(cls.PROVEEDOR)

        return cls._renovar_sesion()

    @classmethod
    def _sesion_activa(
        cls,
        cookies: dict,
    ) -> bool:

        if not cookies:
            return False

        try:
            instance = cls._get_instance()

            response = requests.get(
                instance.CLIENTES_URL,
                cookies=cookies,
                allow_redirects=False,
                timeout=10,
            )

            if response.status_code == 302:
                location = response.headers.get("Location", "")

                if location.rstrip("/") == instance.BASE_URL.rstrip("/"):
                    return False

            return response.status_code == 200

        except Exception:
            logger.exception("Error validando sesión TechSmart.")
            return False

    @classmethod
    def _renovar_sesion(cls) -> dict:

        try:
            instance = cls._get_instance()

            payload = {
                "rfc": current_app.config["TECHSMART_RFC"],
                "usuario": current_app.config["TECHSMART_USUARIO"],
                "txtPass": current_app.config["TECHSMART_PASSWORD"],
            }

            response = requests.post(
                instance.LOGIN_URL,
                data=payload,
                timeout=15,
            )

            response.raise_for_status()

            cookies = response.cookies.get_dict()

            if not cookies:
                raise Exception("No se recibieron cookies.")

            cls._guardar_sesion(cookies)

            logger.info("Sesión TechSmart renovada.")

            return cookies

        except Exception:
            logger.exception("Error autenticando TechSmart.")
            return {}

    @classmethod
    def _guardar_sesion(
        cls,
        cookies: dict,
    ):

        SesionProveedorService.guardar(
            proveedor=cls.PROVEEDOR,
            cookies=cookies,
        )

    @classmethod
    def _parsear_catalogo(
        cls,
        html: str,
        cookies: dict,
        sku_buscado: str | None,
        base_url: str,
    ) -> ProductoProveedor | None:

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        cards = soup.select(".card.rounded")

        for card in cards:
            try:
                modelo = cls._obtener_modelo(card)

                if sku_buscado and modelo.upper() != sku_buscado.upper():
                    continue

                codigo = cls._obtener_codigo(card)

                if not codigo:
                    continue

                existencias = cls._obtener_existencias(
                    codigo,
                    cookies,
                )

                return ProductoProveedor(
                    proveedor="TECHSMART",
                    nombre=cls._obtener_nombre(card),
                    precio=cls._obtener_precios(card)[0],
                    moneda="USD",
                    existencia=sum(x.existencia for x in existencias),
                    descuento=cls._obtener_precios(card)[1],
                    existencias_sucursal=existencias,
                    url=None,
                    url_imagen=cls._obtener_imagen(card, base_url),
                )

            except Exception:
                logger.exception("Error parseando producto.")

        return None

    @classmethod
    def _obtener_existencias(
        cls,
        codigo: str,
        cookies: dict,
    ) -> list[ExistenciaSucursal]:

        try:
            instance = cls._get_instance()

            response = requests.post(
                instance.EXISTENCIAS_URL,
                data={
                    "codArt": codigo,
                },
                cookies=cookies,
                timeout=10,
            )

            response.raise_for_status()

            data = response.json()

            if data.get("error") != "no":
                return []

            patron = re.compile(r"Sucursal\s+(.*?):\s+(\d+)\s+pza\(s\)")

            return [
                ExistenciaSucursal(
                    sucursal=sucursal.strip(),
                    existencia=int(cantidad),
                )
                for sucursal, cantidad in patron.findall(
                    data.get(
                        "msg",
                        "",
                    )
                )
            ]

        except Exception:
            logger.exception("Error obteniendo existencias.")
            return []

    @staticmethod
    def _obtener_nombre(card) -> str:

        nodo = card.select_one(".text-card")

        return nodo.get_text(" ", strip=True) if nodo else ""

    @staticmethod
    def _obtener_modelo(card) -> str:

        nodo = card.select_one(".codigo-producto")

        if not nodo:
            return ""

        match = re.search(
            r"MODELO:\s*([^\s]+)",
            nodo.get_text(
                " ",
                strip=True,
            ),
        )

        return match.group(1) if match else ""

    @staticmethod
    def _obtener_codigo(card) -> str | None:

        boton = card.select_one('[onclick*="muestraExistencias"]')

        if not boton:
            return None

        match = re.search(
            r"muestraExistencias\('([^']+)'",
            boton.get(
                "onclick",
                "",
            ),
        )

        return match.group(1) if match else None

    @staticmethod
    def _obtener_precios(card) -> tuple[Decimal, Decimal | None]:

        precios = []

        for font in card.select("font"):
            texto = font.get_text(strip=True)

            if "$" not in texto or "USD" not in texto:
                continue

            try:
                precios.append(
                    Decimal(
                        texto.replace("$", "")
                        .replace("USD", "")
                        .replace(",", "")
                        .strip()
                    )
                )

            except Exception:
                continue

        if len(precios) >= 2:
            return (
                precios[0],
                precios[1],
            )

        if len(precios) == 1:
            return (
                precios[0],
                None,
            )

        return (
            Decimal("0"),
            None,
        )

    @classmethod
    def _obtener_imagen(
        cls,
        card,
        base_url: str,
    ) -> str | None:

        imagen = card.select_one(".img-catalogo")

        if not imagen:
            return None

        src = imagen.get("src")

        if not src:
            return None

        return f"{base_url}/{src.removeprefix('../')}"
