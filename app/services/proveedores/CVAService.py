from decimal import Decimal
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from flask import current_app

from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.models.producto_proveedor import ProductoProveedor, ExistenciaSucursal


class CVAService(ProveedorProductos):

    @staticmethod
    def _build_url(params: dict) -> str:
        query = urlencode(params)
        return f"{current_app.config['CVA_URL']}?{query}"

    @staticmethod
    def _make_request(params: dict):
        url = CVAService._build_url(params)

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return CVAService._parse_xml(response.content)

        except requests.RequestException as e:
            print(f"Error en la petición: {e}")
            return []

    @staticmethod
    def _parse_xml(xml_data: bytes) -> list[ProductoProveedor]:
        resultados = []

        try:
            root = ET.fromstring(xml_data)

            for item in root.findall("item"):

                existencias_sucursal = []

                # CVA no envía VENTAS_CDMX explícitamente.
                existencia_cdmx = int(item.findtext("disponible") or 0)

                existencias_sucursal.append(
                    ExistenciaSucursal(
                        sucursal="VENTAS CDMX",
                        existencia=existencia_cdmx
                    )
                )

                existencia_total = existencia_cdmx

                for campo in item:

                    nombre_campo = campo.tag

                    if nombre_campo in {
                        "CENTRO_DE_DISTRIBUCION_MEXICO",
                        "CENTRO_DE_DISTRIBUCION_MONTERREY",
                        "RETAIL_CDMX",
                        "RETAIL_MTY",
                    } or nombre_campo.startswith("VENTAS_"):

                        try:
                            existencia = int(campo.text or 0)
                        except (TypeError, ValueError):
                            existencia = 0

                        if existencia > 0:
                            existencias_sucursal.append(
                                ExistenciaSucursal(
                                    sucursal=nombre_campo.replace("_", " "),
                                    existencia=existencia
                                )
                            )

                            existencia_total += existencia

                descuento = item.findtext("PrecioDescuento")
                
                moneda = (item.findtext("moneda") or "").strip().lower()

                if moneda in {"pesos", "mxn"}:
                    moneda = "MXN"
                elif moneda in {"dolares", "usd"}:
                    moneda = "USD"
                else:
                    moneda = moneda.upper() if moneda else "DESCONOCIDA"

                producto = ProductoProveedor(
                    proveedor="CVA",
                    nombre=item.findtext("descripcion") or "",
                    precio=Decimal(item.findtext("precio") or "0"),
                    moneda=moneda,
                    existencia=existencia_total,
                    descuento=(
                        Decimal(descuento)
                        if descuento and descuento.strip()
                        else None
                    ),
                    existencias_sucursal=existencias_sucursal,
                    url=None,
                    url_imagen=item.findtext("imagen")
                )

                resultados.append(producto)

        except ET.ParseError as e:
            print(f"Error parseando XML: {e}")

        return resultados

    @staticmethod
    def _buscar_por_codigo(codigo: str):
        params = {
            "cliente": current_app.config["CVA_CLIENTE"],
            "codigo": codigo,
            "promos": "1",
            "sucursales": "1"
        }

        return CVAService._make_request(params)

    @staticmethod
    def buscar_producto(texto: str) -> ProductoProveedor:
        resultados = CVAService._buscar_por_codigo(texto)

        if not resultados:
            return None

        return resultados[0]