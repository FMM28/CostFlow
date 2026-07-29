import logging
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from concurrent.futures import (
    TimeoutError as FutureTimeoutError,
)

from flask import current_app

from app.cache.productos_cache_service import ProductosCacheService
from app.models.producto_proveedor import ProductoProveedor
from app.services.proveedores import (
    AindiService,
    CVAService,
    ExelService,
    GlomaService,
    PCELService,
    PCHService,
    ProveedoresBDService,
    SiclikService,
    SyscomService,
    TechSmartService,
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
        PCHService
    ]

    MAX_WORKERS = 24
    TIMEOUT_GLOBAL_SEGUNDOS = 50
    _executor: ThreadPoolExecutor | None = None

    @classmethod
    def _get_executor(cls) -> ThreadPoolExecutor:
        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(
                max_workers=cls.MAX_WORKERS,
                thread_name_prefix="buscador-producto",
            )
        return cls._executor

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
    def _buscar_en_bd(
        cls, app, nombre: str, sku: str
    ) -> tuple[list[ProductoProveedor], str | None]:
        with app.app_context():
            try:
                return ProveedoresBDService.buscar_producto(
                    nombre=nombre, sku=sku
                ), None
            except Exception as e:
                logger.exception("Error al consultar BD.")
                return [], f"BD: {str(e)}"

    @classmethod
    def buscar(cls, nombre=None, sku=None):

        nombre = (nombre or "").strip()
        sku = (sku or "").strip()

        if not nombre and not sku:
            logger.warning("Se llamó a buscar() sin nombre ni SKU.")
            return [], []

        app = current_app._get_current_object()
        cache = ProductosCacheService()
        executor = cls._get_executor()

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
        # 2. WORKERS (proveedores externos + BD en paralelo)
        # -------------------------
        faltantes = proveedores_externos_keys - proveedores_cacheados
        providers_to_query = [provider_map[p] for p in faltantes]

        nuevos_externos: list[ProductoProveedor] = []

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

        bd_future = executor.submit(cls._buscar_en_bd, app, nombre, sku)
        futures[bd_future] = "BD"

        pendientes = set(futures.keys())

        try:
            for future in as_completed(futures, timeout=cls.TIMEOUT_GLOBAL_SEGUNDOS):
                pendientes.discard(future)
                nombre_tarea = futures[future]

                try:
                    if future is bd_future:
                        bd_resultados, error = future.result()
                        resultados.extend(bd_resultados)
                    else:
                        resultado, error = future.result()
                        if resultado:
                            resultados.append(resultado)
                            nuevos_externos.append(resultado)

                    if error:
                        errores.append(error)

                except Exception as e:
                    errores.append(f"{nombre_tarea}: {str(e)}")

        except FutureTimeoutError:
            pendientes_nombres = [futures[f] for f in pendientes]
            logger.warning(
                "Timeout global alcanzado (%ss). Pendientes sin respuesta: %s",
                cls.TIMEOUT_GLOBAL_SEGUNDOS,
                pendientes_nombres,
            )
            for nombre_tarea in pendientes_nombres:
                errores.append(f"{nombre_tarea}: timeout global")

        # -------------------------
        # 3. CACHE UPDATE
        # -------------------------
        if sku and nuevos_externos:
            cache.set(sku, nuevos_externos)

        # -------------------------
        # 4. FILTER + SORT
        # -------------------------
        final = [p for p in resultados if p.existencia and p.existencia > 0]

        final.sort(
            key=lambda p: (
                p.descuento if p.descuento and p.descuento > 0 else p.precio,
                -(p.existencia or 0),
            )
        )

        return final, errores
