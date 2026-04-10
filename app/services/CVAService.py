import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from flask import current_app


class CVAService:

    DEFAULT_PARAMS = {
        "cliente": "%s" % current_app.config.get("CVA_CLIENTE"),
        "marca": "%",
        "grupo": "%",
        "clave": "%",
        "codigo": "%"
    }

    @staticmethod
    def _build_url(params: dict) -> str:
        query = urlencode(params)
        return f"{CVAService.current_app.config['CVA_URL']}?{query}"

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
    def _parse_xml(xml_data: bytes):
        resultados = []

        try:
            root = ET.fromstring(xml_data)

            for item in root.findall("item"):
                articulo = {
                    "clave": item.findtext("clave"),
                    "codigo_fabricante": item.findtext("codigo_fabricante"),
                    "descripcion": item.findtext("descripcion"),
                    "precio": float(item.findtext("precio") or 0),
                    "moneda": item.findtext("moneda"),
                    "disponible": int(item.findtext("disponible") or 0),
                    "imagen": item.findtext("imagen"),
                }
                resultados.append(articulo)

        except ET.ParseError as e:
            print(f"Error parseando XML: {e}")

        return resultados

    @staticmethod
    def buscar_por_marca(marca: str):
        params = CVAService.DEFAULT_PARAMS.copy()
        params["marca"] = marca
        return CVAService._make_request(params)

    @staticmethod
    def buscar_por_grupo(grupo: str):
        params = CVAService.DEFAULT_PARAMS.copy()
        params["grupo"] = grupo
        return CVAService._make_request(params)

    @staticmethod
    def buscar_por_clave(clave: str):
        params = CVAService.DEFAULT_PARAMS.copy()
        params["clave"] = clave
        return CVAService._make_request(params)

    @staticmethod
    def buscar_por_codigo(codigo: str):
        params = CVAService.DEFAULT_PARAMS.copy()
        params["codigo"] = codigo
        return CVAService._make_request(params)

    @staticmethod
    def buscar_por_marca_y_grupo(marca: str, grupo: str):
        params = CVAService.DEFAULT_PARAMS.copy()
        params["marca"] = marca
        params["grupo"] = grupo
        return CVAService._make_request(params)
    
if __name__ == "__main__":
    resultados = CVAService.buscar_por_marca("amd")

    for r in resultados[:5]:
        print(r)