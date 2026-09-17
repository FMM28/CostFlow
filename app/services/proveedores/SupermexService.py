import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from flask import current_app

from app.models.producto_proveedor import ProductoProveedor
from app.services.proveedor_credenciales_service import ProveedorCredencialesService
from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.services.sesion_proveedor_service import SesionProveedorService

logger = logging.getLogger(__name__)


class SuperMexService(ProveedorProductos):
    PROVEEDOR = "SUPERMEX"

    def __init__(self):
        base = current_app.config["SUPERMEX_URL"].rstrip("/")
        self.BASE_URL = base
        self.LOGIN_URL = f"{base}/en/web/login"
        self.LOGIN_POST_URL = f"{base}/web/login"
        self.BUSCADOR_URL = f"{base}/en/shop"
        self.CUENTA_URL = f"{base}/en/my"

    @classmethod
    def _get_instance(cls):
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _get_session(cls):
        if not hasattr(cls, "_session"):
            cls._session = requests.Session()
        return cls._session

    @classmethod
    def buscar_producto(cls, nombre=None, sku=None):
        termino = sku or nombre
        if not termino:
            return None

        cookies = cls._obtener_cookies_validas()
        if not cookies:
            return None

        ins = cls._get_instance()
        session = cls._get_session()

        session.cookies.clear()
        session.cookies.update(cookies)

        r = session.get(
            ins.BUSCADOR_URL,
            params={"search": termino},
            timeout=15,
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        products_grid = soup.select_one("#products_grid")
        if not products_grid:
            return None

        producto = products_grid.select_one(
            "div.tp-product-item"
        )
        if not producto:
            return None

        enlace = producto.select_one(
            "a.tp-product-image-container[href]"
        )
        if not enlace:
            return None

        url_detalle = urljoin(
            ins.BASE_URL + "/",
            enlace["href"],
        )

        nombre_elemento = producto.select_one(
            "a.tp-product-title"
        )

        if not nombre_elemento:
            nombre_elemento = producto.select_one(
                '[itemprop="name"]'
            )

        precio_elemento = producto.select_one(
            '[itemprop="price"]'
        )

        moneda_elemento = producto.select_one(
            '[itemprop="priceCurrency"]'
        )

        imagen_elemento = producto.select_one(
            'img[itemprop="image"]'
        )

        nombre_producto = (
            nombre_elemento.get("content")
            if nombre_elemento and nombre_elemento.get("content")
            else nombre_elemento.get_text(strip=True)
            if nombre_elemento
            else termino
        )

        precio = None
        if precio_elemento:
            try:
                precio = float(precio_elemento.get("content", precio_elemento.get_text(strip=True)))
            except (TypeError, ValueError):
                try:
                    precio = float(precio_elemento.get_text(strip=True).replace(",", ""))
                except (TypeError, ValueError):
                    logger.exception(
                        "Error procesando precio de SUPERMEX para SKU: %s",
                        termino,
                    )

        moneda = (
            moneda_elemento.get("content")
            if moneda_elemento and moneda_elemento.get("content")
            else "MXN"
        )

        url_imagen = None
        if imagen_elemento and imagen_elemento.get("src"):
            url_imagen = urljoin(
                ins.BASE_URL + "/",
                imagen_elemento["src"],
            )

        return ProductoProveedor(
            proveedor=cls.PROVEEDOR,
            nombre=nombre_producto,
            precio=precio,
            moneda=moneda,
            existencia=1,
            descuento=None,
            existencias_sucursal=None,
            url=url_detalle,
            url_imagen=url_imagen,
        )

    @classmethod
    def _obtener_cookies_validas(cls):
        cookies = SesionProveedorService.obtener(cls.PROVEEDOR)

        if cookies:
            if cls._sesion_activa(cookies):
                return cookies

            SesionProveedorService.eliminar(cls.PROVEEDOR)

        return cls._autenticar()

    @classmethod
    def _sesion_activa(cls, cookies):
        if not cookies:
            return False

        try:
            ins = cls._get_instance()
            session = cls._get_session()

            session.cookies.clear()
            session.cookies.update(cookies)

            r = session.get(
                ins.CUENTA_URL,
                timeout=10,
                allow_redirects=True,
            )

            r.raise_for_status()

            return cls._es_pagina_cuenta(r.url)

        except Exception:
            logger.exception("Error validando sesión de SUPERMEX.")
            return False

    @classmethod
    def _es_pagina_cuenta(cls, url):
        ins = cls._get_instance()

        login_url = ins.LOGIN_URL.rstrip("/")
        cuenta_url = ins.CUENTA_URL.rstrip("/")

        url_sin_fragmento = url.split("#", 1)[0].rstrip("/")

        if url_sin_fragmento.startswith(login_url):
            return False

        return url_sin_fragmento == cuenta_url

    @classmethod
    def _autenticar(cls):
        credenciales = ProveedorCredencialesService.obtener(cls.PROVEEDOR)

        if credenciales is None:
            raise RuntimeError(
                f"No existen credenciales configuradas para {cls.PROVEEDOR}"
            )

        email = credenciales.get("email")
        password = credenciales.get("password")

        if not email or not password:
            raise RuntimeError(
                f"Las credenciales de {cls.PROVEEDOR} están incompletas"
            )

        ins = cls._get_instance()
        session = cls._get_session()

        session.cookies.clear()

        r = session.get(
            ins.LOGIN_URL,
            timeout=15,
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        csrf_elemento = soup.select_one(
            'input[name="csrf_token"]'
        )

        if not csrf_elemento:
            raise RuntimeError(
                "No se encontró csrf_token en la página de login de SUPERMEX"
            )

        csrf_token = csrf_elemento.get("value")

        if not csrf_token:
            raise RuntimeError(
                "El csrf_token de SUPERMEX está vacío"
            )

        r = session.post(
            ins.LOGIN_POST_URL,
            data={
                "csrf_token": csrf_token,
                "login": email,
                "password": password,
                "type": "password",
            },
            timeout=15,
            allow_redirects=True,
        )
        r.raise_for_status()

        cookies = session.cookies.get_dict()

        if not cookies:
            raise RuntimeError(
                "No se obtuvieron cookies después del login de SUPERMEX"
            )

        if not cls._es_pagina_cuenta(r.url):
            raise RuntimeError(
                "La autenticación de SUPERMEX no fue exitosa"
            )

        cls._guardar_sesion(cookies)

        return cookies

    @classmethod
    def _guardar_sesion(cls, cookies):
        SesionProveedorService.guardar(
            proveedor=cls.PROVEEDOR,
            cookies=cookies,
        )