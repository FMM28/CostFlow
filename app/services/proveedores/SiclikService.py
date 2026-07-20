import logging

from decimal import Decimal

import requests

from flask import current_app

from app.models.producto_proveedor import ProductoProveedor, ExistenciaSucursal

from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.services.sesion_proveedor_service import SesionProveedorService


logger = logging.getLogger(__name__)


class SiclikService(ProveedorProductos):
    LOGIN_URL = "https://login.siclik.mx"

    FARGATE_URL = "https://fargate.siclik.mx:8997"

    AUTH_URL = f"{FARGATE_URL}/auth/siclik"

    CLIENT_ID = "4bd253db-ef76-41f8-a464-288a662cb08d"

    REDIRECT_URI = f"{FARGATE_URL}/auth/siclik/callback"

    _session = None

    _oauth_state = None

    @classmethod
    def _new_session(cls):

        session = requests.Session()

        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/149.0.0.0 "
                    "Safari/537.36"
                ),
                "Accept": "application/json",
                "Accept-Language": "es-419,es;q=0.7",
            }
        )

        return session

    @classmethod
    def _guardar_sesion_bd(cls):

        if not cls._session:
            return

        cookies = []

        for cookie in cls._session.cookies:
            cookies.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.secure,
                }
            )

        SesionProveedorService.guardar(
            proveedor="SICLIK",
            cookies=cookies,
        )

        logger.info("Sesión Siclik almacenada")

    @classmethod
    def _cargar_sesion_bd(cls):

        cookies = SesionProveedorService.obtener("SICLIK")

        if not cookies:
            return False

        session = cls._new_session()

        for cookie in cookies:
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie["domain"],
                path=cookie["path"],
            )

        cls._session = session

        return True

    @classmethod
    def _validar_sesion(cls):

        if not cls._session:
            return False

        try:
            response = cls._session.get(
                "https://siclik.mx/comercio",
                headers={
                    "Origin": "https://siclik.mx",
                    "Referer": "https://siclik.mx/",
                },
                timeout=10,
            )

            return response.status_code == 200

        except Exception:
            return False

    @classmethod
    def _get_session(cls):

        if cls._session:
            if cls._validar_sesion():
                return cls._session

            cls._session = None

        if cls._cargar_sesion_bd():
            if cls._validar_sesion():
                return cls._session

            SesionProveedorService.eliminar("SICLIK")
            cls._session = None

        raise Exception("Sesión Siclik expirada")

    @classmethod
    def iniciar_autenticacion(cls):

        session = cls._new_session()

        response = session.get(cls.AUTH_URL, allow_redirects=True, timeout=20)

        url = response.url

        cls._oauth_state = url.split("state=")[1].split("&")[0]

        payload = {
            "email": current_app.config["SICLIK_EMAIL"],
            "password": current_app.config["SICLIK_PASSWORD"],
            "clientId": cls.CLIENT_ID,
            "state": cls._oauth_state,
            "redirectUri": cls.REDIRECT_URI,
        }

        response = session.post(
            f"{cls.LOGIN_URL}/api/auth/signin", json=payload, timeout=20
        )

        response.raise_for_status()

        response = session.post(
            f"{cls.LOGIN_URL}/api/auth/send-2fa",
            json={"source": "login", "channel": "whatsapp"},
            timeout=20,
        )

        response.raise_for_status()

        cls._session = session

        logger.info("Código MFA enviado")

    @classmethod
    def confirmar_autenticacion(cls, codigo):

        session = cls._session

        payload = {
            "source": "Login",
            "code": codigo,
            "rememberDevice": True,
            "clientId": cls.CLIENT_ID,
            "redirectUri": cls.REDIRECT_URI,
            "state": cls._oauth_state,
        }

        response = session.post(
            f"{cls.LOGIN_URL}/api/auth/confirm-mfa", json=payload, timeout=20
        )

        response.raise_for_status()

        response = session.get(
            f"{cls.LOGIN_URL}/api/auth/redirect",
            params={
                "state": cls._oauth_state,
                "redirectUri": cls.REDIRECT_URI,
                "customerId": current_app.config["SICLIK_CUSTOMER_ID"],
            },
            allow_redirects=False,
            timeout=20,
        )

        response.raise_for_status()

        callback = response.headers.get("Location")

        response = session.get(callback, allow_redirects=True, timeout=20)

        response.raise_for_status()

        if not cls._validar_sesion():
            raise Exception("No fue posible crear la sesión Siclik")

        cls._guardar_sesion_bd()

        logger.info("Autenticación completada")

    @classmethod
    def sesion_activa(cls):

        try:
            cls._get_session()
            return True

        except Exception:
            return False

    @classmethod
    def _eliminar_sesion_bd(cls):
        try:
            SesionProveedorService.eliminar("SICLIK")
            logger.info("Sesión Siclik eliminada")
        except Exception as e:
            logger.error(f"Error al eliminar sesión: {e}")

    @classmethod
    def _obtener_detalle(cls, sku):
        try:
            response = cls._get_session().get(
                f"{cls.FARGATE_URL}/product-catalog/details/{sku}",
                params={"allowVariants": "false"},
                headers={
                    "Origin": "https://siclik.mx",
                    "Referer": "https://siclik.mx/",
                },
                timeout=15,
            )

            if response.status_code == 404:
                return None

            if response.status_code == 401:
                logger.warning(
                    f"Error 401 al obtener detalle de {sku}, eliminando cookies"
                )
                cls._eliminar_sesion_bd()
                cls._session = None
                raise requests.exceptions.HTTPError(
                    "La sesion de Siclik Compusoluciones ha vencido."
                )

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error al obtener detalle de {sku}: {e}")
            raise

    @staticmethod
    def _parse_existencias(item):

        existencias = []

        total = 0

        inventario = item.get("inventory", {})

        for stock in inventario.get("stock", []):
            cantidad = int(stock.get("quantity", 0))

            if cantidad <= 0:
                continue

            almacen = stock.get("warehouse", "N/A")

            existencias.append(
                ExistenciaSucursal(sucursal=f"WAREHOUSE {almacen}", existencia=cantidad)
            )

            total += cantidad

        return total, existencias

    @staticmethod
    def _parse_item(item):

        total, existencias = SiclikService._parse_existencias(item)

        precio = Decimal(str(item.get("price", 0)))

        precio_promocion = Decimal(str(item.get("promotionPrice", 0)))

        descuento = precio_promocion if precio_promocion > 0 else None

        imagen = None

        imagenes = item.get("images", [])

        if imagenes:
            imagen = (
                imagenes[0].get("thumbnail")
                or imagenes[0].get("medium")
                or imagenes[0].get("low")
            )

        return ProductoProveedor(
            proveedor="SICLIK",
            nombre=item.get("title", ""),
            precio=precio,
            moneda=item.get("currency", "MXN"),
            existencia=total,
            descuento=descuento,
            existencias_sucursal=existencias,
            url=(
                f"https://siclik.mx/productos/pd/{item.get('title', '').replace(' ', '-').lower()}/{item.get('sku', '')}"
            ),
            url_imagen=imagen,
        )

    @staticmethod
    def buscar_producto(nombre=None, sku=None):
        if not sku:
            return None

        try:
            item = SiclikService._obtener_detalle(sku)

            if item is None:
                return None

            return SiclikService._parse_item(item)

        except Exception as e:
            logger.error(f"Error Siclik al buscar SKU {sku}: {e}")
            raise
