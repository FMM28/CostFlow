import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import current_app

from app.models.producto_proveedor import ProductoProveedor
from app.cache.productos_cache_service import ProductosCacheService
from app.services.proveedores import (
    CVAService,
    SyscomService,
    SiclikService,
    TechSmartService,
    GlomaService,
    PCELService,
    AindiService,
    ProveedoresBDService,
    ExelService,
)

logger = logging.getLogger(__name__)


class BuscadorProducto:
    PROVEEDORES_EXTERNOS = [
        CVAService,
        SyscomService,
        SiclikService,
        TechSmartService,
        GlomaService,
        PCELService,
        AindiService,
        ExelService,
    ]

    MAX_WORKERS = 4

    @classmethod
    def _nombre_proveedor(cls, proveedor_service) -> str:
        return proveedor_service.__name__.replace("Service", "").upper()

    @classmethod
    def _buscar_en_proveedor(
        cls,
        app,
        proveedor,
        nombre: str | None,
        sku: str | None,
    ) -> tuple[ProductoProveedor | None, str | None]:

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
                    logger.debug("Resultado encontrado en %s.", nombre_proveedor)
                    return resultado, None

                logger.debug("Sin resultados en %s.", nombre_proveedor)
                return None, None

            except Exception as e:
                logger.exception("Error al consultar %s.", nombre_proveedor)
                return None, f"{nombre_proveedor}: {str(e)}"

    @classmethod
    def buscar(cls, nombre=None, sku=None):

        nombre = (nombre or "").strip()
        sku = (sku or "").strip()

        if not nombre and not sku:
            logger.warning("Se llamó a buscar() sin nombre ni SKU.")
            return [], []

        app = current_app._get_current_object()
        cache = ProductosCacheService()

        resultados: list[ProductoProveedor] = []
        errores: list[str] = []

        provider_map = {cls._nombre_proveedor(p): p for p in cls.PROVEEDORES_EXTERNOS}
        proveedores_externos_keys = set(provider_map.keys())

        # -------------------------
        # 1. CACHE
        # -------------------------
        cached = cache.get(sku) if sku else None
        proveedores_cacheados: set[str] = set()

        if cached:
            for proveedor_nombre, producto in cached.items():
                resultados.append(producto)
                proveedores_cacheados.add(proveedor_nombre.upper())

            logger.debug("Resultados cacheados: %s", list(cached.keys()))

        # -------------------------
        # 2. WORKERS
        # -------------------------
        faltantes = proveedores_externos_keys - proveedores_cacheados
        providers_to_query = [provider_map[p] for p in faltantes]

        nuevos_externos: list[ProductoProveedor] = []

        if providers_to_query:
            with ThreadPoolExecutor(
                max_workers=min(cls.MAX_WORKERS, len(providers_to_query)),
            ) as executor:
                futures = {
                    executor.submit(
                        cls._buscar_en_proveedor,
                        app,
                        proveedor,
                        nombre,
                        sku,
                    ): proveedor.__name__
                    for proveedor in providers_to_query
                }

                for future in as_completed(futures):
                    try:
                        resultado, error = future.result()

                        if resultado:
                            resultados.append(resultado)
                            nuevos_externos.append(resultado)

                        if error:
                            errores.append(error)

                    except Exception as e:
                        errores.append(str(e))

        # -------------------------
        # 3. BD
        # -------------------------
        bd_resultados = ProveedoresBDService.buscar_producto(
            nombre=nombre,
            sku=sku,
        )

        resultados.extend(bd_resultados)

        # -------------------------
        # 4. CACHE UPDATE
        # -------------------------
        if sku and nuevos_externos:
            cache.set(sku, nuevos_externos)

        # -------------------------
        # 5. FILTER + SORT
        # -------------------------
        final = [p for p in resultados if p.existencia and p.existencia > 0]

        final.sort(
            key=lambda p: (
                p.descuento if p.descuento and p.descuento > 0 else p.precio,
                -(p.existencia or 0),
            )
        )

        return final, errores
