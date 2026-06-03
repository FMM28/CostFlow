import logging
from app.services.proveedores.CVAService import CVAService
from app.models.producto_proveedor import ProductoProveedor

logger = logging.getLogger(__name__)


class BuscadorProducto:
    PROVEEDORES = [
        CVAService,
    ]

    @classmethod
    def buscar(cls, texto: str) -> list[ProductoProveedor]:
        """Busca un producto en todos los proveedores registrados."""
        if not texto or not texto.strip():
            logger.warning("Se llamó a buscar() con un texto vacío o nulo.")
            return []

        logger.info(
            "Iniciando búsqueda para: '%s' en %d proveedor(es).",
            texto,
            len(cls.PROVEEDORES),
        )
        resultados: list[ProductoProveedor] = []

        for servicio in cls.PROVEEDORES:
            nombre = servicio.__name__
            try:
                logger.debug("Buscando en %s...", nombre)
                resultado = servicio.buscar_producto(texto)

                if resultado:
                    resultados.append(resultado)
                    logger.debug("Resultado encontrado en %s.", nombre)
                else:
                    logger.debug("Sin resultados en %s.", nombre)

            except Exception:
                logger.exception("Error inesperado al buscar en %s.", nombre)

        resultados.sort(
            key=lambda p: (p.precio, -(p.existencia or 0))
        )

        logger.info(
            "Búsqueda finalizada. %d/%d proveedor(es) retornaron resultados.",
            len(resultados),
            len(cls.PROVEEDORES),
        )
        return resultados