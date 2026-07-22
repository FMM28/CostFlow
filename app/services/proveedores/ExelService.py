import logging
import re
import threading
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.models.producto_proveedor import (
    ExistenciaSucursal,
    ProductoProveedor,
)
from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.services.sesion_proveedor_service import SesionProveedorService
from app.services.proveedor_credenciales_service import ProveedorCredencialesService

logger = logging.getLogger(__name__)


class ExelLoginError(RuntimeError):
    """No fue posible iniciar sesión en Exel (credenciales, Turnstile, etc.)."""


class ExelSesionInvalidaError(RuntimeError):
    """La sesión de Exel no es válida y no pudo restablecerse."""


class ExelPasswordDesactualizadaError(RuntimeError):
    """Exel exige actualizar la contraseña de la cuenta antes de continuar."""


class ExelService(ProveedorProductos):
    PROVEEDOR = "EXEL"
    BASE_URL = "https://www.exel.com.mx/xlstore"
    LOGIN_URL = f"{BASE_URL}/Acceso"
    BUSCADOR_URL = f"{BASE_URL}/Productos/buscar.aspx"
    ACTUALIZAR_PASSWORD_PATH = "/ActualizarPassword"

    _lock = threading.RLock()

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    IMPERSONATE = "chrome124"

    @classmethod
    def _guardar_cookies(cls, cookies):
        if not cookies:
            return

        SesionProveedorService.guardar(
            proveedor=cls.PROVEEDOR,
            cookies=cookies,
        )

    @classmethod
    def _cargar_cookies(cls):
        cookies = SesionProveedorService.obtener(cls.PROVEEDOR)

        if cookies is None:
            return []

        return cookies

    @staticmethod
    def _cookies_de_sesion_http(sesion):
        cookies = []
        try:
            for cookie in sesion.cookies.jar:
                cookies.append(
                    {
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": cookie.domain,
                        "path": cookie.path or "/",
                        "expires": cookie.expires if cookie.expires else -1,
                        "secure": bool(cookie.secure),
                    }
                )
        except Exception as e:
            logger.warning(f"No se pudieron extraer cookies de la sesión HTTP: {e}")

        return cookies

    @classmethod
    def _crear_sesion_http(cls, cookies=None):
        sesion = cffi_requests.Session(impersonate=cls.IMPERSONATE)
        sesion.headers.update(
            {
                "User-Agent": cls.USER_AGENT,
                "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        for cookie in cookies or []:
            try:
                sesion.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain") or "www.exel.com.mx",
                    path=cookie.get("path", "/"),
                )
            except Exception as e:
                logger.warning(
                    f"No se pudo aplicar la cookie '{cookie.get('name')}': {e}"
                )

        return sesion

    @classmethod
    def _verificar_redirect_password(cls, url):
        if cls.ACTUALIZAR_PASSWORD_PATH.lower() in (url or "").lower():
            raise ExelPasswordDesactualizadaError(
                "Es necesario actualizar la contraseña de Exel"
            )

    @classmethod
    def _sesion_valida_http(cls, sesion):
        try:
            respuesta = sesion.get(cls.BASE_URL + "/", timeout=20, allow_redirects=True)
        except Exception as e:
            logger.warning(f"No se pudo verificar la sesión vía HTTP: {e}")
            return False

        cls._verificar_redirect_password(respuesta.url)
        return "/Acceso" not in respuesta.url

    @classmethod
    def _aplicar_stealth(cls, context):
        """Reduce algunas señales comunes de detección de automatización."""
        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['es-MX', 'es', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );
            """
        )

    @classmethod
    def _hacer_login(cls, context, page):
        credenciales = ProveedorCredencialesService.obtener(proveedor=cls.PROVEEDOR)

        if credenciales is None:
            raise ExelLoginError("No existen credenciales configuradas para Exel")

        usuario = credenciales.get("usuario")
        password = credenciales.get("password")

        if not usuario or not password:
            raise ExelLoginError("Las credenciales de Exel están incompletas")

        if not usuario or not password:
            raise ExelLoginError("Credenciales de Exel no configuradas")

        try:
            page.goto(cls.LOGIN_URL, wait_until="networkidle", timeout=30000)
            page.fill("#MainContent_txtUsuario", usuario)
            page.fill("#MainContent_txtPassword", password)
            page.click("#btnAceptar")
        except Exception as e:
            raise ExelLoginError(
                f"Login fallido - error interactuando con el formulario: {e}"
            ) from e

        try:
            page.wait_for_url(lambda url: "/Acceso" not in url, timeout=45000)
        except Exception as e:
            raise ExelLoginError("Login fallido - no se pudo salir de /Acceso") from e

        cls._verificar_redirect_password(page.url)

        if "/Acceso" in page.url:
            raise ExelLoginError("Login fallido - Turnstile no resuelto")

        cls._guardar_cookies(context.cookies())

    @classmethod
    def _abrir_contexto_autenticado(cls, playwright):
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
        context = browser.new_context(
            user_agent=cls.USER_AGENT,
            locale="es-MX",
            viewport={"width": 1366, "height": 768},
            timezone_id="America/Mexico_City",
        )
        cls._aplicar_stealth(context)

        cookies = cls._cargar_cookies()
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception as e:
                logger.warning(f"No se pudieron aplicar cookies al navegador: {e}")

        page = context.new_page()

        try:
            page.goto(cls.BASE_URL + "/", wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            browser.close()
            raise ExelSesionInvalidaError(
                f"No se pudo cargar Exel para validar la sesión: {e}"
            ) from e

        cls._verificar_redirect_password(page.url)

        if "/Acceso" in page.url:
            SesionProveedorService.eliminar(cls.PROVEEDOR)
            cls._hacer_login(context, page)

            cls._verificar_redirect_password(page.url)

            if "/Acceso" in page.url:
                browser.close()
                raise ExelSesionInvalidaError("Sesión inválida después de login")

        return browser, context, page

    @classmethod
    def _reautenticar(cls):

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError("Playwright no instalado") from e

        with sync_playwright() as playwright:
            browser, context, page = cls._abrir_contexto_autenticado(playwright)
            try:
                cookies = context.cookies()
            finally:
                context.close()
                browser.close()

        cls._guardar_cookies(cookies)
        return cls._crear_sesion_http(cookies)

    @staticmethod
    def _parse_precio(texto):
        if not texto:
            return Decimal("0")

        texto_limpio = re.sub(r"[^\d,.]", "", texto)

        if "." not in texto_limpio and "," not in texto_limpio:
            try:
                return Decimal(texto_limpio)
            except Exception as e:
                logger.warning(f"No se pudo convertir el precio '{texto}': {e}")
                return Decimal("0")

        texto_limpio = texto_limpio.replace(",", "")
        try:
            return Decimal(texto_limpio)
        except Exception:
            texto_alternativo = re.sub(r"[^\d.]", "", texto.replace(",", "."))
            try:
                return Decimal(texto_alternativo)
            except Exception as e:
                logger.warning(
                    f"No se pudo convertir el precio '{texto}' (alternativo): {e}"
                )
                return Decimal("0")

    @classmethod
    def _parse_resultado_busqueda(cls, html, sku):
        soup = BeautifulSoup(html, "html.parser")

        selectores = [
            "div.contenedor-producto",
            "div.producto",
            "div[class*='producto']",
        ]

        contenedores = []
        for selector in selectores:
            contenedores = soup.select(selector)
            if contenedores:
                break

        for producto in contenedores:
            codigo_tag = producto.select_one("span[tag='codigo']")
            if not codigo_tag:
                codigo_tag = producto.select_one(
                    ".codigo, .sku, [class*='codigo'], [class*='sku']"
                )

            if not codigo_tag:
                continue

            codigo = re.sub(
                r"^Código:\s*", "", codigo_tag.get_text(strip=True), flags=re.IGNORECASE
            ).strip()

            if sku.upper() not in codigo.upper():
                continue

            nombre_tag = producto.select_one("span[tag='descripcion']")
            if not nombre_tag:
                nombre_tag = producto.select_one(
                    ".descripcion, [class*='descripcion'], .nombre, [class*='nombre']"
                )
            nombre = nombre_tag.get_text(" ", strip=True) if nombre_tag else ""

            precio_tag = producto.select_one("span.span_precio_producto")
            if not precio_tag:
                precio_tag = producto.select_one(".precio, [class*='precio']")
            precio = cls._parse_precio(
                precio_tag.get_text(" ", strip=True) if precio_tag else "0"
            )

            img_tag = producto.select_one("img.imgproducto")
            if not img_tag:
                img_tag = producto.select_one("img[src*='producto']")
            imagen = img_tag.get("src", "") if img_tag else ""

            detalle_tag = producto.select_one("a.BUSCADOR--Detalle__Link")
            if not detalle_tag:
                detalle_tag = producto.select_one(
                    "a[href*='detalle'], a[href*='producto']"
                )
            detalle = detalle_tag.get("href", "") if detalle_tag else ""

            existencia_tag = producto.select_one("span.span_existencia_nacional")
            if not existencia_tag:
                existencia_tag = producto.select_one(
                    ".existencia, [class*='existencia']"
                )

            existencia = 0
            if existencia_tag:
                try:
                    numeros = re.findall(r"\d+", existencia_tag.get_text(strip=True))
                    existencia = int(numeros[0]) if numeros else 0
                except (ValueError, IndexError) as e:
                    logger.warning(f"No se pudo interpretar la existencia: {e}")

            return {
                "nombre": nombre,
                "precio": precio,
                "imagen": imagen,
                "url": detalle,
                "existencia": existencia,
            }

        return None

    @classmethod
    def _obtener_existencias(cls, sesion, url):
        if not url.startswith("http"):
            url = urljoin(cls.BASE_URL, url)

        try:
            respuesta = sesion.get(url, timeout=20, allow_redirects=True)
        except Exception as e:
            logger.error(f"Error obteniendo existencias de {url}: {e}", exc_info=True)
            return [], 0

        cls._verificar_redirect_password(respuesta.url)

        if respuesta.status_code != 200:
            logger.error(
                f"Exel respondió con estado {respuesta.status_code} al obtener "
                f"existencias de {url}"
            )
            return [], 0

        soup = BeautifulSoup(respuesta.text, "html.parser")
        tabla = soup.select_one("#existenciaLocalidad table tbody")

        if not tabla:
            return [], 0

        existencias = []
        total = 0

        for fila in tabla.select("tr"):
            columnas = fila.select("td")
            if len(columnas) < 2:
                continue

            sucursal = columnas[0].get_text(" ", strip=True)
            match = re.search(r"\d+", columnas[1].get_text())
            cantidad = int(match.group()) if match else 0

            if not any(e.sucursal == sucursal for e in existencias):
                existencias.append(
                    ExistenciaSucursal(sucursal=sucursal, existencia=cantidad)
                )
                total += cantidad

        return existencias, total

    @classmethod
    def _crear_producto(cls, sesion, datos):
        existencias, total = cls._obtener_existencias(sesion, datos["url"])

        if total == 0:
            total = datos.get("existencia", 0)

        url_imagen = datos["imagen"]
        if url_imagen and not url_imagen.startswith("http"):
            url_imagen = urljoin(cls.BASE_URL, url_imagen)

        url_producto = datos["url"]
        if url_producto and not url_producto.startswith("http"):
            url_producto = urljoin(cls.BASE_URL, url_producto)

        return ProductoProveedor(
            proveedor=cls.PROVEEDOR,
            nombre=datos["nombre"],
            precio=datos["precio"],
            moneda="MXN",
            existencia=total,
            descuento=None,
            existencias_sucursal=existencias,
            url=url_producto,
            url_imagen=url_imagen,
        )

    @classmethod
    def buscar_producto(cls, nombre=None, sku=None):
        if not sku:
            return None

        with cls._lock:
            cookies = cls._cargar_cookies()
            sesion = cls._crear_sesion_http(cookies)
            if not cls._sesion_valida_http(sesion):
                sesion = cls._reautenticar()

            try:
                url_busqueda = f"{cls.BUSCADOR_URL}?busqueda={sku}"
                respuesta = sesion.get(url_busqueda, timeout=30, allow_redirects=True)

                cls._verificar_redirect_password(respuesta.url)

                if respuesta.url != url_busqueda:
                    logger.info(f"Redirect a: {respuesta.url}")

                if respuesta.status_code != 200:
                    logger.error(
                        f"Exel respondió con estado {respuesta.status_code} al "
                        f"buscar '{sku}'"
                    )
                    return None

                datos = cls._parse_resultado_busqueda(respuesta.text, sku)

                if not datos:
                    return None

                return cls._crear_producto(sesion, datos)

            except ExelPasswordDesactualizadaError:
                raise

            except Exception as e:
                logger.error(f"Error buscando producto {sku}: {e}", exc_info=True)
                return None

            finally:
                try:
                    cls._guardar_cookies(cls._cookies_de_sesion_http(sesion))
                except Exception as e:
                    logger.error(
                        f"Error guardando cookies al cerrar: {e}", exc_info=True
                    )
