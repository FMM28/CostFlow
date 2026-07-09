import logging
from decimal import Decimal
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from flask import current_app

from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.models.producto_proveedor import ProductoProveedor, ExistenciaSucursal

logger = logging.getLogger(__name__)


class CVAService(ProveedorProductos):
    _CAMPOS_SUCURSAL = {
        "CENTRO_DE_DISTRIBUCION_MEXICO",
        "CENTRO_DE_DISTRIBUCION_MONTERREY",
        "RETAIL_CDMX",
        "RETAIL_MTY",
    }

    _MONEDAS_MXN = {"pesos", "mxn"}
    _MONEDAS_USD = {"dolares", "usd"}

    @staticmethod
    def _build_url(params: dict) -> str:
        query = urlencode(params)
        return f"{current_app.config['CVA_URL']}?{query}"

    @staticmethod
    def _make_request(params: dict) -> list[ProductoProveedor]:
        url = CVAService._build_url(params)

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return CVAService._parse_xml(response.content)

        except requests.RequestException as e:
            logger.error("Error en la petición a CVA: %s", e)
            return []

    @staticmethod
    def _parse_existencias(item: ET.Element) -> tuple[int, list[ExistenciaSucursal]]:
        """Parsea las existencias por sucursal de un item del XML de CVA"""
        existencias_sucursal = []

        # CVA no envía VENTAS_CDMX explícitamente.
        existencia_cdmx = int(item.findtext("disponible") or 0)
        existencias_sucursal.append(
            ExistenciaSucursal(sucursal="VENTAS CDMX", existencia=existencia_cdmx)
        )
        existencia_total = existencia_cdmx

        for campo in item:
            nombre_campo = campo.tag

            if nombre_campo in CVAService._CAMPOS_SUCURSAL or nombre_campo.startswith(
                "VENTAS_"
            ):
                try:
                    existencia = int(campo.text or 0)
                except (TypeError, ValueError):
                    existencia = 0

                if existencia > 0:
                    existencias_sucursal.append(
                        ExistenciaSucursal(
                            sucursal=nombre_campo.replace("_", " "),
                            existencia=existencia,
                        )
                    )
                    existencia_total += existencia

        return existencia_total, existencias_sucursal

    @staticmethod
    def _parse_moneda(item: ET.Element) -> str:
        moneda = (item.findtext("moneda") or "").strip().lower()

        if moneda in CVAService._MONEDAS_MXN:
            return "MXN"
        if moneda in CVAService._MONEDAS_USD:
            return "USD"
        return moneda.upper() if moneda else "DESCONOCIDA"

    @staticmethod
    def _parse_item(item: ET.Element) -> ProductoProveedor:
        existencia_total, existencias_sucursal = CVAService._parse_existencias(item)

        descuento = item.findtext("PrecioDescuento").strip()
        precio = Decimal(item.findtext("precio") or "0")

        if descuento == "Sin Descuento":
            descuento = 0.0

        descuento = Decimal(descuento)

        if precio == descuento:
            descuento = Decimal(0.0)

        return ProductoProveedor(
            proveedor="CVA",
            nombre=item.findtext("descripcion") or "",
            precio=precio,
            moneda=CVAService._parse_moneda(item),
            existencia=existencia_total,
            descuento=descuento,
            existencias_sucursal=existencias_sucursal,
            url=None,
            url_imagen=item.findtext("imagen"),
        )

    @staticmethod
    def _parse_xml(xml_data: bytes) -> list[ProductoProveedor]:
        resultados = []

        try:
            root = ET.fromstring(xml_data)

            for item in root.findall("item"):
                try:
                    resultados.append(CVAService._parse_item(item))
                except Exception as e:
                    logger.error("Error procesando item de CVA: %s", e)
                    continue

        except ET.ParseError as e:
            logger.error("Error parseando XML de CVA: %s", e)

        return resultados

    @staticmethod
    def _buscar_por_codigo(codigo: str) -> list[ProductoProveedor]:
        params = {
            "cliente": current_app.config["CVA_CLIENTE"],
            "codigo": codigo,
            "promos": "1",
            "sucursales": "1",
        }

        return CVAService._make_request(params)

    @staticmethod
    def buscar_producto(
        nombre: str | None = None, sku: str | None = None
    ) -> ProductoProveedor | None:
        """
        Busca un producto por su código (SKU) en CVA.
        Retorna None si no se encuentra o si ocurre algún error.
        """
        if not sku:
            logger.warning("Se intentó buscar producto en CVA sin SKU")
            return None

        resultados = CVAService._buscar_por_codigo(sku)

        if not resultados:
            return None

        producto = resultados[0]
        return producto
