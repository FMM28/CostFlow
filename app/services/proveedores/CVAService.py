from decimal import Decimal
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from flask import current_app

from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.models.producto_proveedor import ProductoProveedor


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

                producto = ProductoProveedor(
                    proveedor="CVA",
                    nombre=item.findtext("descripcion") or "",
                    precio=Decimal(item.findtext("precio") or "0"),
                    moneda=item.findtext("moneda") or "MXN",
                    existencia=int(item.findtext("disponible") or 0),
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
            "marca": "%",
            "grupo": "%",
            "clave": "%",
            "codigo": codigo,
        }

        return CVAService._make_request(params)

    @staticmethod
    def buscar_producto(texto: str) -> ProductoProveedor:
        resultados = CVAService._buscar_por_codigo(texto)

        if not resultados:
            raise ValueError(
                f"No se encontró el producto '{texto}' en CVA"
            )

        return resultados[0]