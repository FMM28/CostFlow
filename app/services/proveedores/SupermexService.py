import json
import logging
import re
from decimal import Decimal
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

    COMBINATION_URL = "/website_sale/get_combination_info"

    def __init__(self):
        base = current_app.config["SUPERMEX_URL"].rstrip("/")

        self.BASE_URL = base
        self.LOGIN_URL = f"{base}/en/web/login"
        self.LOGIN_POST_URL = f"{base}/web/login"
        self.BUSCADOR_URL = f"{base}/en/shop"
        self.CUENTA_URL = f"{base}/en/my"
        self.COMBINATION_ENDPOINT = f"{base}{self.COMBINATION_URL}"

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

        try:
            r = session.get(
                ins.BUSCADOR_URL,
                params={"search": termino},
                timeout=15,
            )
            r.raise_for_status()
        except requests.RequestException:
            logger.exception(
                "Error buscando producto de SUPERMEX para: %s",
                termino,
            )
            return None

        soup = BeautifulSoup(
            r.text,
            "html.parser",
        )

        formulario = cls._obtener_formulario_producto(
            soup
        )

        if formulario is None:
            logger.warning(
                "No se encontró formulario de producto de SUPERMEX "
                "para: %s",
                termino,
            )
            return None

        product_id = cls._obtener_input_entero(
            formulario,
            "product_id",
        )

        product_template_id = cls._obtener_input_entero(
            formulario,
            "product_template_id",
        )

        if product_id is None or product_template_id is None:
            logger.warning(
                "No se pudieron obtener product_id/product_template_id "
                "de SUPERMEX para: %s",
                termino,
            )
            return None

        enlace = formulario.select_one(
            "a.tp-product-image-container[href]"
        )

        if not enlace:
            enlace = formulario.select_one(
                'a[itemprop="url"][href]'
            )

        if not enlace:
            logger.warning(
                "No se encontró URL de detalle de SUPERMEX para: %s",
                termino,
            )
            return None

        url_detalle = urljoin(
            ins.BASE_URL + "/",
            enlace["href"],
        )

        nombre_elemento = formulario.select_one(
            "a.tp-product-title"
        )

        if not nombre_elemento:
            nombre_elemento = formulario.select_one(
                '[itemprop="name"]'
            )

        nombre_producto = (
            nombre_elemento.get("content")
            if nombre_elemento
            and nombre_elemento.get("content")
            else nombre_elemento.get_text(strip=True)
            if nombre_elemento
            else termino
        )

        imagen_elemento = formulario.select_one(
            'img[itemprop="image"]'
        )

        url_imagen = None

        if imagen_elemento and imagen_elemento.get("src"):
            url_imagen = urljoin(
                ins.BASE_URL + "/",
                imagen_elemento["src"],
            )

        detalle = cls._obtener_informacion_producto(
            url_detalle=url_detalle,
            product_id=product_id,
            product_template_id=product_template_id,
        )

        if detalle is None:
            return None

        precio = detalle.get("price")

        if precio is not None:
            try:
                precio = Decimal(
                    str(precio)
                ) / Decimal("1.16")
            except (
                TypeError,
                ValueError,
                ArithmeticError,
            ):
                logger.exception(
                    "Error procesando precio de SUPERMEX para SKU: %s",
                    termino,
                )
                precio = None

        moneda = detalle.get(
            "currency"
        ) or "MXN"

        existencia = cls._obtener_existencia(
            detalle.get("free_qty")
        )

        codigo_interno = detalle.get(
            "codigo_interno"
        )

        imagen_detalle = detalle.get(
            "image_url"
        )

        if imagen_detalle:
            url_imagen = urljoin(
                ins.BASE_URL + "/",
                imagen_detalle,
            )

        return ProductoProveedor(
            proveedor=cls.PROVEEDOR,
            nombre=detalle.get(
                "display_name"
            ) or nombre_producto,
            precio=precio,
            moneda=moneda,
            existencia=existencia,
            descuento=None,
            existencias_sucursal=None,
            url=url_detalle,
            url_imagen=url_imagen,
            codigo_interno=codigo_interno,
            sku=None,
        )

    @classmethod
    def _obtener_formulario_producto(cls, soup):
        formulario = soup.select_one(
            'form[itemtype="http://schema.org/Product"]'
        )

        if formulario:
            return formulario

        formulario = soup.select_one(
            "form.tp-product-item"
        )

        if formulario:
            return formulario

        products_grid = soup.select_one(
            "#products_grid"
        )

        if not products_grid:
            return None

        return products_grid.select_one(
            "form"
        )

    @classmethod
    def _obtener_informacion_producto(
        cls,
        url_detalle,
        product_id,
        product_template_id,
    ):
        ins = cls._get_instance()
        session = cls._get_session()

        try:
            r = session.get(
                url_detalle,
                timeout=15,
            )
            r.raise_for_status()
        except requests.RequestException:
            logger.exception(
                "Error obteniendo detalle de producto de SUPERMEX: %s",
                url_detalle,
            )
            return None

        soup = BeautifulSoup(
            r.text,
            "html.parser",
        )

        combination = cls._obtener_combination(
            soup
        )

        csrf_token = cls._obtener_csrf_token(
            soup
        )

        payload = {
            "id": 7,
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "product_template_id": product_template_id,
                "product_id": product_id,
                "combination": combination,
                "add_qty": 1,
                "parent_combination": [],
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": url_detalle,
        }

        if csrf_token:
            headers["X-CSRFToken"] = csrf_token

        try:
            r = session.post(
                ins.COMBINATION_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=15,
            )
            r.raise_for_status()
        except requests.RequestException:
            logger.exception(
                "Error consultando get_combination_info de SUPERMEX "
                "para product_id=%s product_template_id=%s",
                product_id,
                product_template_id,
            )
            return None

        try:
            respuesta = r.json()
        except ValueError:
            logger.error(
                "SUPERMEX devolvió una respuesta que no es JSON "
                "para product_id=%s",
                product_id,
            )
            return None

        result = respuesta.get(
            "result"
        )

        if not isinstance(result, dict):
            logger.warning(
                "Respuesta inválida de get_combination_info de SUPERMEX: %s",
                respuesta,
            )
            return None

        codigo_interno = cls._extraer_codigo_interno(
            result.get("tp_extra_fields")
        )

        image_url = cls._extraer_imagen(
            result.get("carousel")
        )

        tracking_info = result.get(
            "product_tracking_info"
        )

        if not isinstance(
            tracking_info,
            dict,
        ):
            tracking_info = {}

        currency = (
            tracking_info.get("currency")
            or "MXN"
        )

        return {
            "product_id": result.get(
                "product_id",
                product_id,
            ),
            "product_template_id": result.get(
                "product_template_id",
                product_template_id,
            ),
            "display_name": result.get(
                "display_name"
            ),
            "price": result.get(
                "price"
            ),
            "list_price": result.get(
                "list_price"
            ),
            "free_qty": result.get(
                "free_qty"
            ),
            "cart_qty": result.get(
                "cart_qty"
            ),
            "currency": currency,
            "codigo_interno": codigo_interno,
            "image_url": image_url,
            "is_combination_possible": result.get(
                "is_combination_possible"
            ),
            "allow_out_of_stock_order": result.get(
                "allow_out_of_stock_order"
            ),
        }

    @classmethod
    def _obtener_combination(cls, soup):
        valores = []

        selectores = [
            'input[name="product_template_attribute_value_ids"]',
            'input[name="product_template_attribute_value_id"]',
            'input[name="attribute_value_ids"]',
            'input[name="combination"]',
            'input[name="combination_ids"]',
        ]

        for selector in selectores:
            for elemento in soup.select(
                selector
            ):
                valor = cls._obtener_id_entero(
                    elemento.get("value")
                )

                if (
                    valor is not None
                    and valor not in valores
                ):
                    valores.append(valor)

        for elemento in soup.select(
            'input[type="radio"]:checked, '
            'input[type="checkbox"]:checked'
        ):
            valor = cls._obtener_id_entero(
                elemento.get("value")
            )

            if (
                valor is not None
                and valor not in valores
            ):
                valores.append(valor)

        for elemento in soup.select(
            "select option:checked"
        ):
            valor = cls._obtener_id_entero(
                elemento.get("value")
            )

            if (
                valor is not None
                and valor not in valores
            ):
                valores.append(valor)

        if valores:
            return valores

        for elemento in soup.select(
            "[data-combination], "
            "[data-combination-ids], "
            "[data-product-template-attribute-value-ids]"
        ):
            for atributo in (
                "data-combination",
                "data-combination-ids",
                "data-product-template-attribute-value-ids",
            ):
                valor = elemento.get(
                    atributo
                )

                if not valor:
                    continue

                encontrados = cls._extraer_ids(
                    valor
                )

                for encontrado in encontrados:
                    if encontrado not in valores:
                        valores.append(
                            encontrado
                        )

        return valores

    @classmethod
    def _obtener_csrf_token(cls, soup):
        elemento = soup.select_one(
            'input[name="csrf_token"]'
        )

        if elemento:
            return elemento.get(
                "value"
            )

        return None

    @classmethod
    def _extraer_codigo_interno(cls, html):
        if not html:
            return None

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        for fila in soup.select("tr"):
            columnas = fila.select("td")

            if len(columnas) < 2:
                continue

            etiqueta = columnas[0].get_text(
                " ",
                strip=True,
            )

            if etiqueta.upper().rstrip(":") != "SKU":
                continue

            valor = columnas[-1].get_text(
                " ",
                strip=True,
            )

            if valor:
                return valor

        texto = soup.get_text(
            " ",
            strip=True,
        )

        match = re.search(
            r"\bSKU\s*:\s*([A-Za-z0-9._/-]+)",
            texto,
            re.IGNORECASE,
        )

        if match:
            return match.group(1)

        return None

    @classmethod
    def _extraer_imagen(cls, html):
        if not html:
            return None

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        imagen = soup.select_one(
            "img[data-zoom-image]"
        )

        if imagen:
            return (
                imagen.get("data-zoom-image")
                or imagen.get("src")
            )

        imagen = soup.select_one(
            "img[src]"
        )

        if imagen:
            return imagen.get(
                "src"
            )

        return None

    @classmethod
    def _obtener_existencia(cls, free_qty):
        if free_qty is None:
            return 0

        try:
            cantidad = Decimal(
                str(free_qty)
            )

            if cantidad <= 0:
                return 0

            return int(cantidad)

        except (
            TypeError,
            ValueError,
            ArithmeticError,
        ):
            logger.warning(
                "No se pudo convertir free_qty de SUPERMEX: %s",
                free_qty,
            )
            return 0

    @classmethod
    def _obtener_input_entero(
        cls,
        formulario,
        nombre,
    ):
        if formulario is None:
            return None

        elemento = formulario.select_one(
            f'input[name="{nombre}"]'
        )

        if elemento is None:
            return None

        return cls._obtener_id_entero(
            elemento.get("value")
        )

    @classmethod
    def _obtener_id_entero(cls, valor):
        if valor is None:
            return None

        try:
            return int(
                str(valor).strip()
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    @classmethod
    def _extraer_ids(cls, valor):
        if valor is None:
            return []

        if isinstance(
            valor,
            list,
        ):
            resultado = []

            for item in valor:
                item_id = cls._obtener_id_entero(
                    item
                )

                if item_id is not None:
                    resultado.append(
                        item_id
                    )

            return resultado

        valor = str(valor).strip()

        if not valor:
            return []

        try:
            convertido = json.loads(
                valor
            )

            if isinstance(
                convertido,
                list,
            ):
                return cls._extraer_ids(
                    convertido
                )
        except (
            ValueError,
            TypeError,
        ):
            pass

        encontrados = re.findall(
            r"\d+",
            valor,
        )

        resultado = []

        for encontrado in encontrados:
            item_id = cls._obtener_id_entero(
                encontrado
            )

            if item_id is not None:
                resultado.append(
                    item_id
                )

        return resultado

    @classmethod
    def _obtener_cookies_validas(cls):
        cookies = SesionProveedorService.obtener(
            cls.PROVEEDOR
        )

        if cookies:
            if cls._sesion_activa(
                cookies
            ):
                return cookies

            SesionProveedorService.eliminar(
                cls.PROVEEDOR
            )

        return cls._autenticar()

    @classmethod
    def _sesion_activa(cls, cookies):
        if not cookies:
            return False

        try:
            ins = cls._get_instance()
            session = cls._get_session()

            session.cookies.clear()
            session.cookies.update(
                cookies
            )

            r = session.get(
                ins.CUENTA_URL,
                timeout=10,
                allow_redirects=True,
            )

            r.raise_for_status()

            return cls._es_pagina_cuenta(
                r.url
            )

        except Exception:
            logger.exception(
                "Error validando sesión de SUPERMEX."
            )
            return False

    @classmethod
    def _es_pagina_cuenta(cls, url):
        ins = cls._get_instance()

        login_url = ins.LOGIN_URL.rstrip("/")
        cuenta_url = ins.CUENTA_URL.rstrip("/")

        url_sin_fragmento = (
            url.split("#", 1)[0]
            .rstrip("/")
        )

        if url_sin_fragmento.startswith(
            login_url
        ):
            return False

        return (
            url_sin_fragmento == cuenta_url
        )

    @classmethod
    def _autenticar(cls):
        credenciales = (
            ProveedorCredencialesService.obtener(
                cls.PROVEEDOR
            )
        )

        if credenciales is None:
            raise RuntimeError(
                f"No existen credenciales configuradas para "
                f"{cls.PROVEEDOR}"
            )

        email = credenciales.get(
            "email"
        )
        password = credenciales.get(
            "password"
        )

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

        soup = BeautifulSoup(
            r.text,
            "html.parser",
        )

        csrf_elemento = soup.select_one(
            'input[name="csrf_token"]'
        )

        if not csrf_elemento:
            raise RuntimeError(
                "No se encontró csrf_token en la página "
                "de login de SUPERMEX"
            )

        csrf_token = csrf_elemento.get(
            "value"
        )

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
                "No se obtuvieron cookies después del login "
                "de SUPERMEX"
            )

        if not cls._es_pagina_cuenta(
            r.url
        ):
            raise RuntimeError(
                "La autenticación de SUPERMEX no fue exitosa"
            )

        cls._guardar_sesion(
            cookies
        )

        return cookies

    @classmethod
    def _guardar_sesion(cls, cookies):
        SesionProveedorService.guardar(
            proveedor=cls.PROVEEDOR,
            cookies=cookies,
        )
