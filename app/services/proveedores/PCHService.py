import logging
from decimal import Decimal

import requests
from flask import current_app

from app.models.producto_proveedor import (
    ExistenciaSucursal,
    ProductoProveedor,
)
from app.services.proveedor_credenciales_service import ProveedorCredencialesService
from app.services.proveedores.proveedor_productos import ProveedorProductos

logger = logging.getLogger(__name__)


class PCHService(ProveedorProductos):
    @staticmethod
    def _post(endpoint: str, payload: dict) -> dict | None:
        url = f"{current_app.config['PCH_URL']}/{endpoint}"

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=15,
            )
            response.raise_for_status()

            data = response.json()

            if data.get("status") != 200:
                logger.error(
                    "PCH respondió con error en %s: %s",
                    endpoint,
                    data.get("message"),
                )
                return None

            return data

        except requests.RequestException as e:
            logger.error("Error realizando petición a PCH: %s", e)
        except ValueError as e:
            logger.error("Respuesta JSON inválida de PCH: %s", e)

        return None

    @staticmethod
    def _obtener_credenciales() -> dict | None:
        credenciales = ProveedorCredencialesService.obtener("PCH")

        if credenciales is None:
            logger.error("No existen credenciales configuradas para PCH")
            return None

        customer = credenciales.get("customer")
        key = credenciales.get("key")

        if not customer or not key:
            logger.error("Las credenciales de PCH están incompletas")
            return None

        return {
            "customer": customer,
            "key": key,
        }

    @staticmethod
    def _obtener_producto(sku: str) -> dict | None:
        payload = PCHService._obtener_credenciales()

        if payload is None:
            return None

        payload["sku"] = sku

        respuesta = PCHService._post("extcust/catalog", payload)

        if respuesta is None:
            return None

        productos = respuesta.get("data", {}).get("productos", [])

        for producto in productos:
            if producto.get("sku") == sku:
                return producto

        return None

    @staticmethod
    def _obtener_existencias(
        sku: str,
    ) -> tuple[int, list[ExistenciaSucursal]]:
        payload = PCHService._obtener_credenciales()

        if payload is None:
            return 0, []

        payload["sku"] = sku

        respuesta = PCHService._post("extcust/getprodstock", payload)

        if respuesta is None:
            return 0, []

        productos = respuesta.get("data", {}).get("productos", [[]])

        registros = productos[0] if productos else []

        existencias = []

        for registro in registros:
            if registro.get("sku") != sku:
                continue

            cantidad = int(registro.get("cantidad", 0))

            if cantidad <= 0:
                continue

            existencias.append(
                ExistenciaSucursal(
                    sucursal=registro.get("almacen", ""),
                    existencia=cantidad,
                )
            )

        existencia_total = sum(suc.existencia for suc in existencias)

        return existencia_total, existencias

    @staticmethod
    def _obtener_precio(
        sku: str,
    ) -> tuple[Decimal, str]:
        payload = PCHService._obtener_credenciales()

        if payload is None:
            return Decimal("0"), "DESCONOCIDA"

        payload["sku"] = sku

        respuesta = PCHService._post(
            "extcust/getprodprice_warehouse",
            payload,
        )

        if respuesta is None:
            return Decimal("0"), "DESCONOCIDA"

        productos = respuesta.get("data", {}).get("productos", [])

        for producto in productos:
            if producto.get("sku") != sku:
                continue

            precios = producto.get("precios", [])

            if not precios:
                return Decimal("0"), producto.get("moneda", "DESCONOCIDA")

            precio = min(Decimal(str(p["precio"])) for p in precios)

            return precio, producto.get("moneda", "DESCONOCIDA")

        return Decimal("0"), "DESCONOCIDA"

    @staticmethod
    def buscar_producto(
        nombre: str | None = None,
        sku: str | None = None,
    ) -> ProductoProveedor | None:
        """
        Busca un producto por SKU en PCH.
        """

        if not sku:
            logger.warning("Se intentó buscar un producto en PCH sin SKU")
            return None

        producto = PCHService._obtener_producto(sku)

        if producto is None:
            return None

        existencia, existencias_sucursal = PCHService._obtener_existencias(sku)

        precio, moneda = PCHService._obtener_precio(sku)

        return ProductoProveedor(
            proveedor="PCH",
            nombre=producto.get("descripcion", ""),
            precio=precio,
            moneda=moneda,
            existencia=existencia,
            descuento=Decimal("0"),
            existencias_sucursal=existencias_sucursal,
            url=None,
            url_imagen=None,
        )
