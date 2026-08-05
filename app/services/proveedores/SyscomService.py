import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

import requests
from flask import current_app

from app.models.producto_proveedor import ExistenciaSucursal, ProductoProveedor
from app.services.proveedor_credenciales_service import ProveedorCredencialesService
from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.services.sesion_proveedor_service import SesionProveedorService

logger = logging.getLogger(__name__)

MARGEN_EXPIRACION = 30


class SyscomService(ProveedorProductos):
    """Servicio para consultar productos de SYSCOM vía API REST"""

    _session: requests.Session | None = None

    PROVEEDOR = "SYSCOM"

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
        return url.rstrip("/")

    @classmethod
    def _get_full_url(cls, endpoint: str) -> str:
        """Construye la URL completa para acceder a la API"""
        base = cls._get_base_url()
        return f"{base}/api/v1{endpoint}"

    @classmethod
    def _sesion_valida(cls) -> bool:
        """
        Determina si el token almacenado sigue vigente.
        """

        sesion = SesionProveedorService.obtener_registro(cls.PROVEEDOR)

        if sesion is None:
            return False

        datos = SesionProveedorService.obtener(cls.PROVEEDOR)

        if not datos:
            return False

        access_token = datos.get("access_token")
        expires_in = datos.get("expires_in")

        if not access_token or expires_in is None:
            return False

        vence_en = sesion.updated_at + timedelta(
            seconds=max(expires_in - MARGEN_EXPIRACION, 0)
        )

        return datetime.now() < vence_en

    @classmethod
    def _guardar_sesion_bd(cls, access_token: str, expires_in: int) -> None:
        SesionProveedorService.guardar(
            proveedor=cls.PROVEEDOR,
            cookies={
                "access_token": access_token,
                "expires_in": expires_in,
            },
        )

    @classmethod
    def _solicitar_nuevo_token(cls) -> Optional[str]:
        """Solicita un nuevo token de acceso mediante client_credentials."""

        credenciales = ProveedorCredencialesService.obtener(cls.PROVEEDOR)

        if credenciales is None:
            logger.error(
                "No existen credenciales configuradas para %s",
                cls.PROVEEDOR,
            )
            return None

        client_id = credenciales.get("client_id")
        client_secret = credenciales.get("client_secret")

        if not client_id or not client_secret:
            logger.error(
                "Las credenciales de %s están incompletas",
                cls.PROVEEDOR,
            )
            return None

        token_url = f"{cls._get_base_url()}/oauth/token"

        try:
            response = cls._get_session().post(
                token_url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=10,
            )

            response.raise_for_status()

            data = response.json()

            access_token = data.get("access_token")
            expires_in = data.get("expires_in", 0)

            if not access_token:
                logger.error("SYSCOM no devolvió access_token en la respuesta")
                return None

            cls._guardar_sesion_bd(access_token, expires_in)

            logger.info(
                "Token de acceso de %s obtenido y persistido en BD",
                cls.PROVEEDOR,
            )

            return access_token

        except requests.RequestException as e:
            logger.error(
                "Error obteniendo token de %s: %s",
                cls.PROVEEDOR,
                e,
            )
            return None

    @classmethod
    def _get_access_token(cls) -> Optional[str]:
        if cls._sesion_valida():
            datos = SesionProveedorService.obtener(cls.PROVEEDOR)
            return datos["access_token"]

        return cls._solicitar_nuevo_token()

    @classmethod
    def _get_headers(cls) -> Optional[dict]:
        """Construye los headers con el token Bearer"""
        token = cls._get_access_token()
        if not token:
            return None
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    @classmethod
    def _buscar_por_modelo(cls, headers: dict, sku: str) -> Optional[dict]:
        url = cls._get_full_url("/productos")
        params = {
            "modelo": sku,
            "moneda": "MXN",
            "inventarios": "true",
        }

        try:
            response = cls._get_session().get(
                url, headers=headers, params=params, timeout=(5, 20)
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict):
                return data

            if isinstance(data, list) and data:
                sku_norm = sku.strip().upper()
                for producto in data:
                    if producto.get("modelo", "").strip().upper() == sku_norm:
                        return producto
                return data[0]

            return None

        except requests.RequestException as e:
            logger.error(
                "Error buscando producto por modelo '%s' en SYSCOM: %s", sku, e
            )
            return None

    @classmethod
    def _buscar_por_texto(cls, headers: dict, nombre: str) -> Optional[dict]:
        url = cls._get_full_url("/productos")
        params = {
            "busqueda": nombre,
            "pagina": 1,
            "limit": 10,
            "moneda": "MXN",
            "inventarios": "true",
        }

        try:
            response = cls._get_session().get(
                url, headers=headers, params=params, timeout=(5, 20)
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()

            productos = data.get("productos", [])
            if not productos:
                logger.info("SYSCOM no devolvió resultados para '%s'", nombre)
                return None

            return productos[0]

        except requests.RequestException as e:
            logger.error(
                "Error buscando producto por texto '%s' en SYSCOM: %s", nombre, e
            )
            return None

    @classmethod
    def _buscar_producto(cls, nombre: str | None, sku: str | None) -> Optional[dict]:
        headers = cls._get_headers()
        if not headers:
            logger.warning("No se pudo obtener headers de autenticación para SYSCOM")
            return None

        if sku:
            producto = cls._buscar_por_modelo(headers, sku)
            if producto:
                return producto

        if nombre:
            return cls._buscar_por_texto(headers, nombre)

        return None

    @classmethod
    def _parse_existencias(cls, data: dict) -> tuple[int, List[ExistenciaSucursal]]:
        """
        Parsea las existencias del producto.
        """
        existencia_data = data.get("existencia")
        if not isinstance(existencia_data, dict):
            return int(data.get("total_existencia", 0) or 0), []

        existencias_sucursal: dict[str, int] = {}

        detalle = existencia_data.get("detalle")
        if isinstance(detalle, dict):
            for sucursales in detalle.values():
                if not isinstance(sucursales, dict):
                    continue
                for sucursal, cantidad in sucursales.items():
                    try:
                        cantidad_int = int(float(cantidad))
                    except (TypeError, ValueError):
                        continue
                    sucursal_norm = sucursal.upper().replace("_", " ")
                    existencias_sucursal[sucursal_norm] = (
                        existencias_sucursal.get(sucursal_norm, 0) + cantidad_int
                    )

        existencias_lista = [
            ExistenciaSucursal(sucursal=sucursal, existencia=cantidad)
            for sucursal, cantidad in existencias_sucursal.items()
        ]

        if "total_existencia" in data:
            existencia_total = int(data.get("total_existencia") or 0)
        else:
            existencia_total = int(existencia_data.get("nuevo", 0) or 0)
            asterisco = existencia_data.get("asterisco", {})
            if isinstance(asterisco, dict):
                for cantidad in asterisco.values():
                    try:
                        existencia_total += int(float(cantidad))
                    except (TypeError, ValueError):
                        continue

        return existencia_total, existencias_lista

    @classmethod
    def _parse_precios(cls, data: dict) -> tuple[Decimal, Optional[Decimal], str]:
        precios = data.get("precios")
        if not isinstance(precios, dict):
            return Decimal("0"), None, "MXN"

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

        moneda = "MXN"
        return precio_lista, descuento, moneda

    @classmethod
    def _get_imagen_principal(cls, data: dict) -> Optional[str]:
        """Obtiene la URL de la imagen principal del producto"""
        img_portada = data.get("img_portada")
        if img_portada:
            return img_portada

        imagenes = data.get("imagenes", [])
        if imagenes:
            return imagenes[0].get("imagen") or imagenes[0].get("url")

        return None

    @classmethod
    def buscar_producto(
        cls, nombre: str | None = None, sku: str | None = None
    ) -> Optional[ProductoProveedor]:
        """
        Busca un producto por su SKU y/o nombre en SYSCOM.
        """
        if not sku and not nombre:
            return None

        data = cls._buscar_producto(nombre, sku)

        if not data:
            logger.info(
                "No se encontró producto (sku='%s', nombre='%s') en SYSCOM", sku, nombre
            )
            return None

        try:
            existencia_total, existencias_sucursal = cls._parse_existencias(data)
            precio, descuento, moneda = cls._parse_precios(data)

            url_producto = f"https://www.syscom.mx/products/{data.get('producto_id')}"

            producto = ProductoProveedor(
                proveedor=cls.PROVEEDOR,
                nombre=data.get("titulo"),
                precio=precio,
                moneda=moneda,
                existencia=existencia_total,
                descuento=descuento,
                existencias_sucursal=existencias_sucursal,
                url=url_producto,
                url_imagen=cls._get_imagen_principal(data),
            )

            return producto

        except Exception as e:
            logger.error(
                "Error procesando datos del producto SYSCOM (sku='%s'): %s", sku, e
            )
            return None
