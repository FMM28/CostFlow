import logging
import time
from decimal import Decimal
from typing import Optional, List
import requests
from flask import current_app

from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.models.producto_proveedor import ProductoProveedor, ExistenciaSucursal

logger = logging.getLogger(__name__)


class SyscomService(ProveedorProductos):
    """Servicio para consultar productos de SYSCOM vía API REST"""

    _token_cache: dict = {"access_token": None, "expires_at": 0}

    _session: Optional[requests.Session] = None

    @classmethod
    def _get_session(cls) -> requests.Session:
        if cls._session is None:
            cls._session = requests.Session()
        return cls._session

    @classmethod
    def _get_base_url(cls) -> str:
        """Obtiene la URL base de la API de SYSCOM desde la configuración"""
        url = current_app.config.get("SYSCOM_URL")
        if not url:
            logger.error("SYSCOM_URL no está configurada")
            raise ValueError("La URL de SYSCOM no está configurada (SYSCOM_URL)")
        return url.rstrip('/')

    @classmethod
    def _get_full_url(cls, endpoint: str) -> str:
        """Construye la URL completa para acceder a la API"""
        base = cls._get_base_url()
        return f"{base}/api/v1{endpoint}"

    @classmethod
    def _get_access_token(cls) -> Optional[str]:
        """
        Obtiene el token de acceso OAuth2 usando client credentials.
        Reutiliza el token mientras no haya expirado para evitar
        solicitudes innecesarias.
        """
        cached_token = cls._token_cache.get("access_token")
        expires_at = cls._token_cache.get("expires_at", 0)

        if cached_token and time.time() < expires_at:
            return cached_token

        token_url = f"{cls._get_base_url()}/oauth/token"
        client_id = current_app.config.get("SYSCOM_CLIENT_ID")
        client_secret = current_app.config.get("SYSCOM_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error(
                "SYSCOM_CLIENT_ID y SYSCOM_CLIENT_SECRET deben estar configurados"
            )
            return None

        try:
            response = cls._get_session().post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            access_token = data.get("access_token")
            # Restamos un margen de seguridad de 30s antes de la expiración real
            expires_in = data.get("expires_in", 0)
            cls._token_cache["access_token"] = access_token
            cls._token_cache["expires_at"] = time.time() + max(expires_in - 30, 0)

            logger.info("Token de acceso de SYSCOM obtenido correctamente")
            return access_token
        except requests.RequestException as e:
            logger.error("Error obteniendo token de SYSCOM: %s", e)
            return None

    @classmethod
    def _get_headers(cls) -> Optional[dict]:
        """Construye los headers con el token Bearer"""
        token = cls._get_access_token()
        if not token:
            return None
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

    @classmethod
    def _buscar_producto(cls, nombre: str | None, sku: str | None) -> Optional[dict]:
        """
        Busca un producto por su nombre o SKU en SYSCOM.
        """
        headers = cls._get_headers()
        if not headers:
            logger.warning("No se pudo obtener headers de autenticación para SYSCOM")
            return None

        url = cls._get_full_url("/productos")

        params = {
            "busqueda": f"{nombre} + {sku}",
            "pagina": 1
        }

        try:
            response = cls._get_session().get(
                url, headers=headers, params=params, timeout=(5, 20)
            )
            response.raise_for_status()
            data = response.json()

            productos = data.get("productos", [])
            if not productos:
                logger.info("SYSCOM no devolvió resultados para '%s'", params["busqueda"])
                return None

            if sku:
                sku_norm = sku.strip().upper()
                for producto in productos:
                    if producto.get("modelo", "").strip().upper() == sku_norm:
                        return producto
                return None

            return productos[0]

        except requests.RequestException as e:
            logger.error("Error buscando producto (sku='%s', nombre='%s') en SYSCOM: %s", sku, nombre, e)
            return None

    @classmethod
    def _parse_existencias(cls, data: dict) -> tuple[int, List[ExistenciaSucursal]]:
        """Parsea las existencias por sucursal del producto"""
        existencias_sucursal = []
        existencia_total = 0

        existencia_data = data.get("existencia", {})

        for sucursal, cantidad in existencia_data.items():
            if isinstance(cantidad, (int, float)):
                cantidad_int = int(cantidad)
                existencias_sucursal.append(
                    ExistenciaSucursal(
                        sucursal=sucursal.upper().replace("_", " "),
                        existencia=cantidad_int
                    )
                )
                existencia_total += cantidad_int

        return existencia_total, existencias_sucursal

    @classmethod
    def _parse_precios(cls, data: dict) -> tuple[Decimal, Optional[Decimal], str]:
        """Parsea los precios del producto"""
        precios = data.get("precios", {})

        precio_lista = Decimal(str(precios.get("precio_lista", 0)))

        precio_especial = precios.get("precio_especial")
        precio_descuento = precios.get("precio_descuento")

        descuento = None
        if precio_especial is not None:
            descuento = Decimal(str(precio_especial))
        if precio_descuento is not None:
            descuento_d = Decimal(str(precio_descuento))
            if descuento is None or descuento_d < descuento:
                descuento = descuento_d

        moneda = "USD"
        return precio_lista, descuento, moneda

    @classmethod
    def _get_imagen_principal(cls, data: dict) -> Optional[str]:
        """Obtiene la URL de la imagen principal del producto"""
        img_portada = data.get("img_portada")
        if img_portada:
            return img_portada

        imagenes = data.get("imagenes", [])
        if imagenes:
            return imagenes[0].get("url")

        return None

    @classmethod
    def buscar_producto(cls, nombre: str | None = None, sku: str | None = None) -> Optional[ProductoProveedor]:
        """
        Busca un producto por su SKU y nombre en SYSCOM.
        """
        if not sku and not nombre:
            return None

        data = cls._buscar_producto(nombre, sku)

        if not data:
            logger.info("No se encontró producto (sku='%s', nombre='%s') en SYSCOM", sku, nombre)
            return None

        try:
            existencia_total, existencias_sucursal = cls._parse_existencias(data)
            precio, descuento, moneda = cls._parse_precios(data)

            url_producto = f"https://www.syscom.mx/products/{data.get('producto_id')}"

            producto = ProductoProveedor(
                proveedor="SYSCOM",
                nombre=data.get("titulo"),
                precio=precio,
                moneda=moneda,
                existencia=existencia_total,
                descuento=descuento,
                existencias_sucursal=existencias_sucursal,
                url=url_producto,
                url_imagen=cls._get_imagen_principal(data)
            )

            return producto

        except Exception as e:
            logger.error("Error procesando datos del producto SYSCOM (sku='%s'): %s", sku, e)
            return None