import logging
import re
import threading
from decimal import Decimal
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from app.models.producto_proveedor import (
    ExistenciaSucursal,
    ProductoProveedor,
)
from app.services.proveedor_credenciales_service import ProveedorCredencialesService
from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.services.sesion_proveedor_service import SesionProveedorService

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

    # Tiempos (ms)
    TIMEOUT_NAVEGACION = 45000
    TIMEOUT_RENDER = 30000
    TIMEOUT_POPUP = 15000

    _lock = threading.RLock()

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    # ------------------------------------------------------------------
    # Sesión / cookies
    # ------------------------------------------------------------------
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

    @classmethod
    def _verificar_redirect_password(cls, url):
        if cls.ACTUALIZAR_PASSWORD_PATH.lower() in (url or "").lower():
            raise ExelPasswordDesactualizadaError(
                "Es necesario actualizar la contraseña de Exel"
            )

    # ------------------------------------------------------------------
    # Playwright: contexto, stealth y login
    # ------------------------------------------------------------------
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

        try:
            page.goto(cls.LOGIN_URL, wait_until="networkidle", timeout=20000)
            page.fill("#MainContent_txtUsuario", usuario)
            page.fill("#MainContent_txtPassword", password)
            page.click("#L_ButtonLogin")
        except Exception as e:
            raise ExelLoginError(
                f"Login fallido - error interactuando con el formulario: {e}"
            ) from e

        try:
            page.wait_for_url(lambda url: "/Acceso" not in url, timeout=20000)
        except Exception as e:
            raise ExelLoginError("Login fallido - no se pudo salir de /Acceso") from e

        cls._verificar_redirect_password(page.url)

        if "/Acceso" in page.url:
            raise ExelLoginError("Login fallido - Turnstile no resuelto")

        cls._guardar_cookies(context.cookies())

    @staticmethod
    def _cerrar(browser, context):
        for recurso in (context, browser):
            if recurso is None:
                continue
            try:
                recurso.close()
            except Exception:
                pass

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
            cls._cerrar(browser, context)
            raise ExelSesionInvalidaError(
                f"No se pudo cargar Exel para validar la sesión: {e}"
            ) from e

        try:
            cls._verificar_redirect_password(page.url)

            if "/Acceso" in page.url:
                SesionProveedorService.eliminar(cls.PROVEEDOR)
                cls._hacer_login(context, page)

                cls._verificar_redirect_password(page.url)

                if "/Acceso" in page.url:
                    raise ExelSesionInvalidaError("Sesión inválida después de login")
        except Exception:
            cls._cerrar(browser, context)
            raise

        return browser, context, page

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------
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

    @staticmethod
    def _normalizar_codigo(texto):
        """Deja solo letras y números en mayúsculas: '100-100001015BOX' -> '100100001015BOX'."""
        return re.sub(r"[^A-Z0-9]", "", (texto or "").upper())

    @classmethod
    def _extraer_datos_producto(cls, producto, codigo):
        nombre_tag = producto.select_one(
            "span[tag='descripcion']"
        ) or producto.select_one(
            ".descripcion, [class*='descripcion'], .nombre, [class*='nombre']"
        )
        nombre = nombre_tag.get_text(" ", strip=True) if nombre_tag else ""

        precio_tag = producto.select_one(
            "span.span_precio_producto"
        ) or producto.select_one(".precio, [class*='precio']")
        precio = cls._parse_precio(
            precio_tag.get_text(" ", strip=True) if precio_tag else "0"
        )

        img_tag = producto.select_one("img.imgproducto") or producto.select_one(
            "img[src*='imgProducto'], img[src*='producto']"
        )
        imagen = img_tag.get("src", "") if img_tag else ""

        detalle_tag = producto.select_one(
            "a.BUSCADOR--Detalle__Link"
        ) or producto.select_one("a[href*='Detalle'], a[href*='detalle']")
        detalle = detalle_tag.get("href", "") if detalle_tag else ""

        popup_tag = producto.select_one(
            "a[id^='lnkAlmacenes'], a[href*='PopUp_producto_y_existencias']"
        )
        url_existencias = popup_tag.get("href", "") if popup_tag else ""

        def _entero(selector):
            tag = producto.select_one(selector)
            if not tag:
                return 0
            numeros = re.findall(r"\d+", tag.get_text(strip=True).replace(",", ""))
            return int(numeros[0]) if numeros else 0

        existencia_nacional = _entero("span.span_existencia_nacional")
        existencia_local = _entero("span.span_existencia_localidad_cliente")

        localidad_tag = producto.select_one("span.span_leyenda_localidad_cliente")
        localidad = (
            localidad_tag.get_text(strip=True).rstrip(":").strip()
            if localidad_tag
            else ""
        )

        return {
            "codigo": codigo,
            "nombre": nombre,
            "precio": precio,
            "imagen": imagen,
            "url": detalle,
            "url_existencias": url_existencias,
            "existencia": existencia_nacional,
            "localidad": localidad,
            "existencia_local": existencia_local,
        }

    @classmethod
    def _parse_resultado_busqueda(cls, html, sku):
        soup = BeautifulSoup(html, "html.parser")

        selectores = [
            "div.buscador-producto",
            "div.contenedor-producto",
            "div.producto",
            "div[class*='producto']",
        ]

        contenedores = []
        for selector in selectores:
            contenedores = soup.select(selector)
            if contenedores:
                break

        if not contenedores:
            logger.warning(f"[Exel] Sin resultados en el HTML para '{sku}'")
            return None

        sku_norm = cls._normalizar_codigo(sku)
        coincidencia_parcial = None

        for producto in contenedores:
            codigo_tag = producto.select_one(
                "span[tag='codigo']"
            ) or producto.select_one(".codigo, .sku, [class*='codigo'], [class*='sku']")
            if not codigo_tag:
                continue

            codigo = re.sub(
                r"^C[oó]digo:\s*",
                "",
                codigo_tag.get_text(" ", strip=True),
                flags=re.IGNORECASE,
            ).strip()

            # Contenedor plantilla (placeholder '-----')
            if not re.search(r"[A-Za-z0-9]", codigo):
                continue

            id_tag = producto.select_one("input[id^='hdnProducto_']")
            id_interno = id_tag.get("value", "").strip() if id_tag else ""

            codigo_norm = cls._normalizar_codigo(codigo)
            id_norm = cls._normalizar_codigo(id_interno)

            exacto = bool(sku_norm) and sku_norm in (codigo_norm, id_norm)
            parcial = bool(sku_norm) and sku_norm in codigo_norm

            if not (exacto or parcial):
                continue

            datos = cls._extraer_datos_producto(producto, codigo)

            if exacto:
                return datos
            if coincidencia_parcial is None:
                coincidencia_parcial = datos

        if coincidencia_parcial is None:
            logger.warning(f"[Exel] Ningún producto coincide con '{sku}'")

        return coincidencia_parcial

    @staticmethod
    def _parse_tabla_existencias(html):
        soup = BeautifulSoup(html, "html.parser")
        filas = soup.select("#existenciaLocalidad table tr") or soup.select("table tr")

        existencias = []
        total = 0

        for fila in filas:
            columnas = fila.select("td")
            if len(columnas) < 2:
                continue

            sucursal = columnas[0].get_text(" ", strip=True)
            match = re.search(r"\d+", columnas[1].get_text().replace(",", ""))
            if not sucursal or not match:
                continue

            cantidad = int(match.group())

            if not any(e.sucursal == sucursal for e in existencias):
                existencias.append(
                    ExistenciaSucursal(sucursal=sucursal, existencia=cantidad)
                )
                total += cantidad

        return existencias, total

    # ------------------------------------------------------------------
    # Navegación con Playwright 
    # ------------------------------------------------------------------
    @classmethod
    def _obtener_html_busqueda(cls, page, sku):
        """Abre la búsqueda y espera a que el JS reemplace los placeholders."""
        url_busqueda = f"{cls.BUSCADOR_URL}?busqueda={quote(sku)}"

        page.goto(
            url_busqueda,
            wait_until="domcontentloaded",
            timeout=cls.TIMEOUT_NAVEGACION,
        )
        cls._verificar_redirect_password(page.url)

        if "/Acceso" in page.url:
            raise ExelSesionInvalidaError("Exel redirigió al login durante la búsqueda")

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        try:
            page.wait_for_function(
                """() => {
                    const tags = document.querySelectorAll("span[tag='codigo']");
                    return Array.from(tags).some(el =>
                        /[A-Za-z0-9]/.test(el.textContent.replace(/C[oó]digo:/i, ''))
                    );
                }""",
                timeout=cls.TIMEOUT_RENDER,
            )
        except Exception:
            logger.warning(f"[Exel] No se cargaron resultados para '{sku}'")
            return None

        return page.content()

    @classmethod
    def _obtener_existencias(cls, context, urls):
        """Prueba cada URL (popup de existencias primero, luego detalle)."""
        for url in urls:
            if not url:
                continue

            if not url.startswith("http"):
                url = urljoin(cls.BASE_URL + "/", url)

            popup = None
            try:
                popup = context.new_page()
                popup.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=cls.TIMEOUT_NAVEGACION,
                )
                cls._verificar_redirect_password(popup.url)

                try:
                    popup.wait_for_selector(
                        "table tr td", timeout=cls.TIMEOUT_POPUP
                    )
                except Exception:
                    pass

                existencias, total = cls._parse_tabla_existencias(popup.content())
                if existencias:
                    return existencias, total

            except ExelPasswordDesactualizadaError:
                raise
            except Exception as e:
                logger.error(
                    f"Error obteniendo existencias de {url}: {e}", exc_info=True
                )
            finally:
                if popup is not None:
                    try:
                        popup.close()
                    except Exception:
                        pass

        return [], 0

    @classmethod
    def _crear_producto(cls, context, datos):
        existencias, total = cls._obtener_existencias(
            context, [datos.get("url_existencias"), datos.get("url")]
        )

        # Respaldo: usar lo que ya venía en el listado
        if not existencias and datos.get("existencia_local"):
            existencias = [
                ExistenciaSucursal(
                    sucursal=datos.get("localidad") or "MEXICO",
                    existencia=datos["existencia_local"],
                )
            ]

        if total == 0:
            total = datos.get("existencia", 0)

        url_imagen = datos["imagen"]
        if url_imagen and not url_imagen.startswith("http"):
            url_imagen = urljoin(cls.BASE_URL + "/", url_imagen)

        url_producto = datos["url"]
        if url_producto and not url_producto.startswith("http"):
            url_producto = urljoin(cls.BASE_URL + "/", url_producto)

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

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    @classmethod
    def buscar_producto(cls, nombre=None, sku=None):
        if not sku:
            return None

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError("Playwright no instalado") from e

        with cls._lock:
            with sync_playwright() as playwright:
                browser = context = None
                try:
                    browser, context, page = cls._abrir_contexto_autenticado(
                        playwright
                    )

                    html = cls._obtener_html_busqueda(page, sku)
                    if not html:
                        return None

                    datos = cls._parse_resultado_busqueda(html, sku)
                    if not datos:
                        return None

                    producto = cls._crear_producto(context, datos)

                    try:
                        cls._guardar_cookies(context.cookies())
                    except Exception as e:
                        logger.error(
                            f"Error guardando cookies: {e}", exc_info=True
                        )

                    return producto

                except (
                    ExelPasswordDesactualizadaError,
                    ExelLoginError,
                    ExelSesionInvalidaError,
                ):
                    raise

                except Exception as e:
                    logger.error(f"Error buscando producto {sku}: {e}", exc_info=True)
                    return None

                finally:
                    cls._cerrar(browser, context)