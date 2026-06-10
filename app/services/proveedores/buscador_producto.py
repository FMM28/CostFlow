import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import current_app

from app.models.producto_proveedor import ProductoProveedor
from app.services.proveedores.CVAService import CVAService
from app.services.proveedores.IngramService import IngramService

logger = logging.getLogger(__name__)


class BuscadorProducto:

    PROVEEDORES = [
        CVAService,
        # IngramService,
    ]

    MAX_WORKERS = 4

    @classmethod
    def _buscar_en_proveedor(
        cls,
        app,
        proveedor,
        texto: str,
    ) -> ProductoProveedor | None:

        with app.app_context():

            nombre = proveedor.__name__

            try:
                logger.debug(
                    "Buscando '%s' en %s...",
                    texto,
                    nombre,
                )

                resultado = proveedor.buscar_producto(texto)

                if resultado:
                    logger.debug(
                        "Resultado encontrado en %s.",
                        nombre,
                    )
                    return resultado

                logger.debug(
                    "Sin resultados en %s.",
                    nombre,
                )

            except Exception:
                logger.exception(
                    "Error al consultar %s.",
                    nombre,
                )

            return None

    @classmethod
    def buscar(
        cls,
        texto: str,
    ) -> list[ProductoProveedor]:

        if not texto or not texto.strip():
            logger.warning(
                "Se llamó a buscar() con un texto vacío o nulo."
            )
            return []

        logger.info(
            "Iniciando búsqueda para '%s' en %d proveedor(es).",
            texto,
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
                    texto,
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