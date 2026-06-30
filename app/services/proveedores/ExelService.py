import logging
import re
import threading
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.producto_proveedor import (
    ExistenciaSucursal,
    ProductoProveedor,
)
from app.models.sesion_proveedor import SesionProveedor
from app.services.proveedores.proveedor_productos import ProveedorProductos

logger = logging.getLogger(__name__)


class ExelService(ProveedorProductos):
    PROVEEDOR = "EXEL"
    BASE_URL = "https://www.exel.com.mx/xlstore"
    LOGIN_URL = f"{BASE_URL}/Acceso"
    BUSCADOR_URL = f"{BASE_URL}/Productos/buscar.aspx"

    _lock = threading.RLock()

    @classmethod
    def _guardar_cookies(cls, cookies):
        try:
            if not cookies:
                return

            registro = SesionProveedor.query.filter_by(proveedor=cls.PROVEEDOR).first()
            if registro is None:
                registro = SesionProveedor(
                    proveedor=cls.PROVEEDOR,
                    cookies={"items": cookies},
                    updated_at=datetime.now(timezone.utc),
                )
                db.session.add(registro)
            else:
                registro.cookies = {"items": cookies}
                registro.updated_at = datetime.now(timezone.utc)

            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.error(f"Error guardando cookies de {cls.PROVEEDOR}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error inesperado guardando cookies: {e}")

    @classmethod
    def _cargar_cookies(cls):
        try:
            registro = SesionProveedor.query.filter_by(proveedor=cls.PROVEEDOR).first()
            if not registro or not registro.cookies:
                return []

            items = (
                registro.cookies.get("items")
                if isinstance(registro.cookies, dict)
                else None
            )
            return items if items else []

        except SQLAlchemyError as e:
            logger.error(f"Error cargando cookies de {cls.PROVEEDOR}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error inesperado cargando cookies: {e}")
            return []

    @classmethod
    def _hacer_login(cls, context, page):
        usuario = current_app.config.get("EXEL_USUARIO", "")
        password = current_app.config.get("EXEL_PASSWORD", "")

        if not usuario or not password:
            raise RuntimeError("Credenciales de Exel no configuradas")

        page.goto(cls.LOGIN_URL, wait_until="networkidle", timeout=30000)
        page.fill("#MainContent_txtUsuario", usuario)
        page.fill("#MainContent_txtPassword", password)
        page.click("#btnAceptar")

        try:
            page.wait_for_url(lambda url: "/Acceso" not in url, timeout=45000)
        except Exception:
            raise RuntimeError("Login fallido - no se pudo salir de /Acceso")

        if "/Acceso" in page.url:
            raise RuntimeError("Login fallido - Turnstile no resuelto")

        cls._guardar_cookies(context.cookies())

    @staticmethod
    def _sesion_valida_en(page):
        try:
            page.goto(
                ExelService.BASE_URL + "/", wait_until="domcontentloaded", timeout=20000
            )
            return "/Acceso" not in page.url
        except Exception:
            return False

    @classmethod
    def _abrir_contexto_autenticado(cls, playwright):
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="es-MX",
            viewport={"width": 1366, "height": 768},
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        cookies = cls._cargar_cookies()
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception as e:
                logger.warning(f"No se pudieron aplicar cookies: {e}")

        page = context.new_page()

        if not cls._sesion_valida_en(page):
            cls._hacer_login(context, page)
            if not cls._sesion_valida_en(page):
                browser.close()
                raise RuntimeError("Sesión inválida después de login")

        return browser, context, page

    @staticmethod
    def _parse_precio(texto):
        if not texto:
            return Decimal("0")

        texto_limpio = re.sub(r"[^\d,.]", "", texto)

        if "." not in texto_limpio and "," not in texto_limpio:
            try:
                return Decimal(texto_limpio)
            except:
                return Decimal("0")

        texto_limpio = texto_limpio.replace(",", "")
        try:
            return Decimal(texto_limpio)
        except Exception:
            texto_alternativo = re.sub(r"[^\d.]", "", texto.replace(",", "."))
            try:
                return Decimal(texto_alternativo)
            except:
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
                except (ValueError, IndexError):
                    pass

            return {
                "nombre": nombre,
                "precio": precio,
                "imagen": imagen,
                "url": detalle,
                "existencia": existencia,
            }

        return None

    @classmethod
    def _obtener_existencias(cls, page, url):
        if not url.startswith("http"):
            url = urljoin(cls.BASE_URL, url)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
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
        except Exception as e:
            logger.error(f"Error obteniendo existencias: {e}")
            return [], 0

    @classmethod
    def _crear_producto(cls, page, datos):
        existencias, total = cls._obtener_existencias(page, datos["url"])

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

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Playwright no instalado")

        with cls._lock:
            with sync_playwright() as playwright:
                browser, context, page = cls._abrir_contexto_autenticado(playwright)

                try:
                    url_busqueda = f"{cls.BUSCADOR_URL}?busqueda={sku}"
                    response = page.goto(
                        url_busqueda, wait_until="networkidle", timeout=30000
                    )

                    if response and response.url != url_busqueda:
                        logger.info(f"Redirect a: {response.url}")

                    try:
                        page.wait_for_selector(
                            "div.contenedor-producto, div.producto, .no-results, .sin-resultados",
                            timeout=15000,
                        )
                    except Exception:
                        return None

                    html = page.content()
                    datos = cls._parse_resultado_busqueda(html, sku)

                    if not datos:
                        return None

                    return cls._crear_producto(page, datos)

                except Exception as e:
                    logger.error(f"Error buscando producto {sku}: {e}")
                    return None

                finally:
                    try:
                        cls._guardar_cookies(context.cookies())
                    except Exception as e:
                        logger.error(f"Error guardando cookies al cerrar: {e}")

                    context.close()
                    browser.close()
