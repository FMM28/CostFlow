import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import current_app

from app.models.producto_proveedor import ProductoProveedor
from app.services.proveedores.CVAService import CVAService
from app.services.proveedores.IngramService import IngramService
from app.services.proveedores.SyscomService import SyscomService
from app.services.proveedores.SiclikService import SiclikService
from app.services.proveedores.TechsmartService import TechSmartService

logger = logging.getLogger(__name__)


class BuscadorProducto:

    PROVEEDORES = [
        CVAService,
        # IngramService,
        SyscomService,
        SiclikService,
        TechSmartService,
    ]

    MAX_WORKERS = 4

    @classmethod
    def _buscar_en_proveedor(
        cls,
        app,
        proveedor,
        nombre: str | None,
        sku: str | None,
    ) -> ProductoProveedor | None:

        with app.app_context():

            nombre_proveedor = proveedor.__name__

            try:
                logger.debug(
                    "Buscando nombre='%s', sku='%s' en %s...",
                    nombre,
                    sku,
                    nombre_proveedor,
                )

                resultado = proveedor.buscar_producto(
                    nombre=nombre,
                    sku=sku,
                )

                if resultado:
                    logger.debug(
                        "Resultado encontrado en %s.",
                        nombre_proveedor,
                    )
                    return resultado

                logger.debug(
                    "Sin resultados en %s.",
                    nombre_proveedor,
                )

            except Exception:
                logger.exception(
                    "Error al consultar %s.",
                    nombre_proveedor,
                )

            return None

    @classmethod
    def buscar(
        cls,
        nombre: str | None = None,
        sku: str | None = None,
    ) -> list[ProductoProveedor]:

        nombre = (nombre or "").strip()
        sku = (sku or "").strip()

        if not nombre and not sku:
            logger.warning(
                "Se llamó a buscar() sin nombre ni SKU."
            )
            return []

        logger.info(
            "Iniciando búsqueda nombre='%s', sku='%s' en %d proveedor(es).",
            nombre,
            sku,
            len(cls.PROVEEDORES),
        )

        resultados: list[ProductoProveedor] = []

        app = current_app._get_current_object()

        max_workers = min(
            cls.MAX_WORKERS,
            len(cls.PROVEEDORES),
        )

        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="proveedor",
        ) as executor:

            futures = {
                executor.submit(
                    cls._buscar_en_proveedor,
                    app,
                    proveedor,
                    nombre,
                    sku,
                ): proveedor.__name__
                for proveedor in cls.PROVEEDORES
            }

            for future in as_completed(futures):

                try:
                    resultado = future.result()

                    if resultado:
                        resultados.append(resultado)

                except Exception:
                    logger.exception(
                        "Error recuperando resultado de búsqueda."
                    )

        resultados.sort(
            key=lambda producto: (
                producto.precio,
                -(producto.existencia or 0),
            )
        )

        logger.info(
            "Búsqueda finalizada. %d/%d proveedor(es) retornaron resultados.",
            len(resultados),
            len(cls.PROVEEDORES),
        )

        return resultados