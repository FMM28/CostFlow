import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from flask import current_app

from app.extensions import db
from app.services.proveedores.proveedor_productos import ProveedorProductos
from app.models.producto_proveedor import ProductoProveedor, ExistenciaSucursal
from app.models.sesion_proveedor import SesionProveedor

logger = logging.getLogger(__name__)


class GlomaService(ProveedorProductos):
    PROVEEDOR = "GLOMA"

    def __init__(self):
        base = current_app.config["GLOMA_URL"].rstrip("/")
        self.BASE_URL = base
        self.LOGIN_URL = f"{base}/componentes/base/datos/login.php"
        self.BUSCADOR_URL = f"{base}/componentes/base/datos/buscador.php"
        self.CUENTA_URL = f"{base}/usuario/cuenta/"

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

        r = session.post(
            ins.BUSCADOR_URL,
            data={"busqueda": termino, "stock": 1},
            timeout=15,
        )
        r.raise_for_status()

        data = r.json()
        productos = data.get("productos", [])
        if not productos:
            return None

        p = productos[0]

        redirect_url = data.get("redirect_url")
        url_detalle = urljoin(ins.BASE_URL + "/", redirect_url)

        return ProductoProveedor(
            proveedor="GLOMA",
            nombre=p["nombre"],
            precio=p["precio"],
            moneda="MXN",
            existencia=p["stock"],
            descuento=None,
            existencias_sucursal=cls._obtener_existencias(session, p["sku"]),
            url=url_detalle,
            url_imagen=f"https://xentra.glomastore.mx/{p['imagen']}",
        )

    @classmethod
    def _obtener_cookies_validas(cls):
        sesion = db.session.get(SesionProveedor, cls.PROVEEDOR)
        if sesion and cls._sesion_activa(sesion.cookies or {}):
            return sesion.cookies
        return cls._autenticar()

    @classmethod
    def _sesion_activa(cls, cookies):
        if not cookies:
            return False
        try:
            ins = cls._get_instance()
            s = cls._get_session()
            s.cookies.clear()
            s.cookies.update(cookies)
            r = s.get(ins.CUENTA_URL, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            return soup.select_one(".xn_cuenta_contenedor__menu-usuario") is not None
        except Exception:
            logger.exception("Error validando sesión.")
            return False

    @classmethod
    def _autenticar(cls):
        ins = cls._get_instance()
        s = cls._get_session()
        r = s.post(
            ins.LOGIN_URL,
            data={
                "usuario": current_app.config["GLOMA_USUARIO"],
                "contrasena": current_app.config["GLOMA_PASSWORD"],
            },
            timeout=15,
        )
        r.raise_for_status()
        cookies = s.cookies.get_dict()
        if "PHPSESSID" not in cookies:
            raise RuntimeError("No se obtuvo PHPSESSID")
        cls._guardar_sesion(cookies)
        return cookies

    @classmethod
    def _guardar_sesion(cls, cookies):
        sesion = db.session.get(SesionProveedor, cls.PROVEEDOR)
        ahora = datetime.now()
        if sesion is None:
            sesion = SesionProveedor(
                proveedor=cls.PROVEEDOR,
                cookies=cookies,
                updated_at=ahora,
            )
            db.session.add(sesion)
        else:
            sesion.cookies = cookies
            sesion.updated_at = ahora
        db.session.commit()

    @classmethod
    def _obtener_existencias(cls, session, sku):
        ins = cls._get_instance()

        r = session.post(
            f"{ins.BASE_URL}/componentes/base/datos/ventana_agregar.php",
            data={"sku": sku, "almacen": "", "operacion": "carrito_cantidad"},
            timeout=15,
        )

        r.raise_for_status()
        data = r.json()

        almacenes = data.get("almacenes", [])
        resultado = []

        for a in almacenes:
            try:
                resultado.append(
                    ExistenciaSucursal(
                        sucursal=a.get("almacen"), existencia=int(a.get("stock", 0))
                    )
                )
            except Exception:
                logger.exception("Error procesando almacen: %s", a)

        return resultado
