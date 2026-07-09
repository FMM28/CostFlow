from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Tuple

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.orden import Orden
from app.models.orden_detalle import OrdenDetalle
from app.services.departamento_unam_service import DepartamentoUNAMService

from datetime import datetime

from app.models.usuario import Usuario

logger = logging.getLogger(__name__)

ESTADOS_VALIDOS = frozenset({"pendiente", "aprobada", "completada", "cancelada"})
TIPOS_COTIZACION = frozenset({"UNAM", "OTROS"})
TERMINOS_CONDICIONES_DEFAULT = """Condiciones de Pago: [CONDICIONES DE PAGO]
[LUGAR DE ENTREGA]
Garantía Directo con Fabricante
No incluye instalación y/o Configuración
Tiempo de Entrega: 4-8 Días hábiles o especificado en partida, una vez confirmada la recepción del pedido u orden de compra y existencia del producto
Precios en Pesos Mexicanos, sujetos a cambios sin previo aviso o por variación del dólar
Emitida la Orden de Compra no se aceptan cancelaciones ni devoluciones."""


class OrdenService:
    @staticmethod
    def get_all(
        id_usuario: Optional[int] = None,
        estado: Optional[str] = None,
    ) -> List[Orden]:
        """
        Retorna todas las órdenes, con filtros opcionales por usuario y estado.

        Returns:
            List[Orden]: Lista de órdenes (vacía si hay error o no hay resultados).
        """
        try:
            query = Orden.query

            if id_usuario is not None:
                query = query.filter_by(id_usuario=id_usuario)

            if estado is not None:
                if estado not in ESTADOS_VALIDOS:
                    logger.warning("Estado de filtro inválido: '%s'", estado)
                    return []
                query = query.filter_by(estado=estado)

            return query.order_by(Orden.fecha_creacion.desc()).all()
        except SQLAlchemyError as exc:
            logger.error("Error al obtener órdenes: %s", exc)
            return []

    @staticmethod
    def get_by_id(id_orden: int) -> Optional[Orden]:
        """
        Retorna una orden por su PK.

        Returns:
            Optional[Orden]: Orden encontrada o None si no existe/hay error.
        """
        try:
            orden = db.session.get(Orden, id_orden)
            if orden is None:
                logger.warning("Orden con id %s no encontrada", id_orden)
            return orden
        except SQLAlchemyError as exc:
            logger.error("Error al buscar orden id=%s: %s", id_orden, exc)
            return None

    @staticmethod
    def get_by_clave(clave_orden: str) -> Optional[Orden]:
        """
        Retorna una orden por su clave única.

        Returns:
            Optional[Orden]: Orden encontrada o None si no existe/hay error.
        """
        if not clave_orden or not clave_orden.strip():
            logger.warning("Clave de orden vacía")
            return None

        try:
            orden = Orden.query.filter_by(clave_orden=clave_orden.strip()).first()
            if orden is None:
                logger.warning("Orden con clave '%s' no encontrada", clave_orden)
            return orden
        except SQLAlchemyError as exc:
            logger.error("Error al buscar orden por clave='%s': %s", clave_orden, exc)
            return None

    @staticmethod
    def _validate_create_data(data: dict) -> Optional[str]:
        """Valida los datos requeridos para crear una orden."""

        if not data.get("id_usuario"):
            return "El campo 'id_usuario' es obligatorio"

        comprador = str(data.get("comprador", "")).strip()
        if not comprador:
            return "El campo 'comprador' es obligatorio"

        estado = data.get("estado", "pendiente")
        if estado not in ESTADOS_VALIDOS:
            return f"Estado '{estado}' no válido. Opciones: {sorted(ESTADOS_VALIDOS)}"

        return None

    @staticmethod
    def _to_decimal(value: any, default: str = "0.00") -> Optional[Decimal]:
        """Convierte un valor a Decimal de forma segura."""
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            logger.warning("Valor inválido para conversión a Decimal: %r", value)
            return Decimal(default)

    @staticmethod
    def create(data: dict) -> Tuple[Optional[Orden], Optional[str]]:
        """
        Crea una nueva orden.

        Campos requeridos: clave_orden, id_usuario, comprador.
        Campos opcionales: estado (default 'pendiente'), total (default 0.00).

        Returns:
            Tuple[Optional[Orden], Optional[str]]: (orden_creada, mensaje_error)
        """
        # Validar datos requeridos
        error = OrdenService._validate_create_data(data)
        if error:
            return None, error

        estado = data.get("estado", "pendiente")
        comprador = str(data["comprador"]).strip()
        total = OrdenService._to_decimal(data.get("total", "0.00"))

        # Crear orden
        try:
            orden = Orden(
                id_usuario=int(data["id_usuario"]),
                comprador=comprador,
                estado=estado,
                total=total,
                terminos_condiciones=TERMINOS_CONDICIONES_DEFAULT,
            )

            db.session.add(orden)
            db.session.commit()
            logger.info(
                "Orden creada: id=%s clave='%s'", orden.id_orden, orden.clave_orden
            )
            return orden, None

        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al crear orden: %s", exc)
            return None, "Error de base de datos al crear la orden"

    @staticmethod
    def update(id_orden: int, data: dict) -> Tuple[Optional[Orden], Optional[str]]:
        """
        Actualiza campos editables de una orden existente.

        Campos actualizables: clave_orden, comprador, estado, total.

        Returns:
            Tuple[Optional[Orden], Optional[str]]: (orden_actualizada, mensaje_error)
        """
        if not data:
            return None, "No se proporcionaron campos para actualizar"

        orden = OrdenService.get_by_id(id_orden)
        if orden is None:
            return None, f"Orden con id {id_orden} no encontrada"

        # Actualizar clave_orden
        if "clave_orden" in data:
            nueva_clave = str(data["clave_orden"]).strip()

            if nueva_clave != orden.clave_orden:
                try:
                    existe = Orden.query.filter_by(clave_orden=nueva_clave).first()
                    if existe:
                        return None, f"Ya existe una orden con la clave '{nueva_clave}'"
                except SQLAlchemyError as exc:
                    logger.error(
                        "Error al verificar nueva clave_orden='%s': %s",
                        nueva_clave,
                        exc,
                    )
                    return None, "Error de base de datos al verificar la clave"

                orden.clave_orden = nueva_clave

        # Actualizar comprador
        if "comprador" in data:
            comprador = str(data["comprador"]).strip()
            if not comprador:
                return None, "El campo 'comprador' no puede estar vacío"
            orden.comprador = comprador

        # Actualizar estado
        if "estado" in data:
            estado = data["estado"]
            if estado not in ESTADOS_VALIDOS:
                return (
                    None,
                    f"Estado '{estado}' no válido. Opciones: {sorted(ESTADOS_VALIDOS)}",
                )
            orden.estado = estado

        # tipo de cotización
        if "tipo_cotizacion" in data and str(data["tipo_cotizacion"]) != "":
            tipo = str(data["tipo_cotizacion"]).strip().upper()

            if tipo not in TIPOS_COTIZACION:
                return (
                    None,
                    f"Tipo de cotización '{tipo}' no válido. Opciones: {sorted(TIPOS_COTIZACION)}",
                )

            orden.tipo_cotizacion = tipo

        # información adicional
        if (
            "tipo_cotizacion" in data
            or "departamento" in data
            or "no_solicitud" in data
            or "proveedor_unam" in data
            or "punto_entrega" in data
        ):
            informacion_actual = orden.informacion_adicional or {}

            informacion, error = OrdenService._validate_informacion_adicional(
                orden.tipo_cotizacion,
                data.get(
                    "departamento",
                    informacion_actual.get("departamento"),
                ),
                data.get(
                    "no_solicitud",
                    informacion_actual.get("no_solicitud"),
                ),
                data.get(
                    "proveedor_unam",
                    informacion_actual.get("proveedor_unam"),
                ),
                data.get(
                    "punto_entrega",
                    informacion_actual.get("punto_entrega"),
                ),
            )

            if error:
                return None, error

            orden.informacion_adicional = informacion

        # Actualizar total
        if "total" in data:
            total = OrdenService._to_decimal(data["total"])
            if total is not None:
                orden.total = total

        # Actualizar fecha_creacion
        if "fecha_creacion" in data:
            try:
                fecha_str = str(data["fecha_creacion"]).strip()
                if fecha_str:
                    orden.fecha_creacion = datetime.strptime(
                        fecha_str, "%Y-%m-%d"
                    ).date()
            except ValueError:
                return None, "Formato de 'fecha_creacion' inválido (use 'YYYY-MM-DD')"

        # vigencia
        if "vigencia" in data:
            try:
                fecha = str(data["vigencia"]).strip()

                vigencia = (
                    datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else None
                )

                fecha_creacion = (
                    orden.fecha_creacion
                    if "fecha_creacion" not in data
                    else datetime.strptime(
                        str(data["fecha_creacion"]).strip(),
                        "%Y-%m-%d",
                    ).date()
                )

                if (
                    vigencia is not None
                    and fecha_creacion is not None
                    and vigencia < fecha_creacion
                ):
                    return (
                        None,
                        "La vigencia no puede ser anterior a la fecha de creación",
                    )

                orden.vigencia = vigencia

            except ValueError:
                return None, "Formato de 'vigencia' inválido (use 'YYYY-MM-DD')"

        # términos y condiciones
        if "terminos_condiciones" in data:
            orden.terminos_condiciones = data["terminos_condiciones"]

        if orden.tipo_cotizacion == "UNAM":
            if orden.terminos_condiciones:
                informacion = orden.informacion_adicional or {}
                punto_entrega = informacion.get("punto_entrega", "").strip()

                lineas = orden.terminos_condiciones.splitlines()

                while len(lineas) < 2:
                    lineas.append("")

                lineas[0] = "Condiciones de Pago: Crédito UNAM"
                lineas[1] = punto_entrega

                orden.terminos_condiciones = "\n".join(lineas)

            if "departamento" in data:
                info_departamento = DepartamentoUNAMService.get_by_nombre(
                    data["departamento"]
                )

                orden.clave_orden = OrdenService._generar_clave_unam(
                    info_departamento.prefijo,
                    orden.clave_orden,
                )

        # incluir firma
        if "incluir_firma" in data:
            orden.incluir_firma = bool(data["incluir_firma"])

        # incluir imagenes
        if "incluir_imagenes" in data:
            orden.incluir_imagenes = bool(data["incluir_imagenes"])

        try:
            db.session.commit()
            logger.info("Orden actualizada: id=%s", id_orden)
            return orden, None
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning(
                "IntegrityError al actualizar orden id=%s: %s", id_orden, exc
            )
            return None, "Conflicto de datos al actualizar la orden"
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al actualizar orden id=%s: %s", id_orden, exc)
            return None, "Error de base de datos al actualizar la orden"

    @staticmethod
    def update_estado(id_orden: int, estado: str) -> Tuple[bool, Optional[str]]:
        """
        Cambia únicamente el estado de una orden, validando el valor permitido.

        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        if estado not in ESTADOS_VALIDOS:
            return (
                False,
                f"Estado '{estado}' no válido. Opciones: {sorted(ESTADOS_VALIDOS)}",
            )

        orden = OrdenService.get_by_id(id_orden)
        if orden is None:
            return False, f"Orden con id {id_orden} no encontrada"

        if orden.estado == estado:
            return True, None  # Ya está en el estado deseado

        try:
            orden.estado = estado
            db.session.commit()
            logger.info("Estado de orden id=%s actualizado a '%s'", id_orden, estado)
            return True, None
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al actualizar estado de orden id=%s: %s", id_orden, exc)
            return False, "Error de base de datos al actualizar el estado"

    @staticmethod
    def recalculate_total(id_orden: int) -> Tuple[Optional[Decimal], Optional[str]]:
        orden = OrdenService.get_by_id(id_orden)

        if orden is None:
            return None, f"Orden con id {id_orden} no encontrada"

        try:
            subtotal = (
                db.session.query(db.func.sum(OrdenDetalle.subtotal))
                .filter_by(id_orden=id_orden)
                .scalar()
            )

            subtotal = Decimal(str(subtotal or 0))

            iva = (subtotal * Decimal("0.16")).quantize(Decimal("0.01"))

            total = subtotal + iva

            orden.subtotal = subtotal
            orden.iva = iva
            orden.total = total

            db.session.commit()

            return total, None

        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al recalcular total de orden id=%s: %s", id_orden, exc)
            return None, "Error de base de datos al recalcular el total"

    @staticmethod
    def delete(id_orden: int) -> Tuple[bool, Optional[str]]:
        """
        Elimina la orden y sus detalles (cascade configurado en el modelo).

        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        orden = OrdenService.get_by_id(id_orden)
        if orden is None:
            return False, f"Orden con id {id_orden} no encontrada"

        try:
            db.session.delete(orden)
            db.session.commit()
            logger.info("Orden eliminada: id=%s", id_orden)
            return True, None
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning("IntegrityError al eliminar orden id=%s: %s", id_orden, exc)
            return (
                False,
                f"No se puede eliminar la orden {id_orden} por restricciones de integridad",
            )
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al eliminar orden id=%s: %s", id_orden, exc)
            return False, "Error de base de datos al eliminar la orden"

    @staticmethod
    def get_with_details(
        id_orden: int,
    ) -> Tuple[Optional[Orden], List[OrdenDetalle], Optional[str]]:
        """
        Obtiene una orden con todos sus detalles.

        Returns:
            Tuple[Optional[Orden], List[OrdenDetalle], Optional[str]]:
                (orden, detalles, mensaje_error)
        """
        orden = OrdenService.get_by_id(id_orden)
        if orden is None:
            return None, [], f"Orden con id {id_orden} no encontrada"

        try:
            detalles = OrdenDetalle.query.filter_by(id_orden=id_orden).all()
            return orden, detalles, None
        except SQLAlchemyError as exc:
            logger.error("Error al obtener detalles de orden id=%s: %s", id_orden, exc)
            return orden, [], "Error al obtener los detalles de la orden"

    @staticmethod
    def get_stats() -> dict:
        """
        Obtiene estadísticas básicas de órdenes.

        Returns:
            dict: Diccionario con estadísticas (vacío si hay error).
        """
        try:
            stats = {}
            for estado in ESTADOS_VALIDOS:
                count = Orden.query.filter_by(estado=estado).count()
                stats[estado] = count

            stats["total"] = sum(stats.values())

            # Total en dinero de órdenes completadas
            total_completadas = (
                db.session.query(db.func.sum(Orden.total))
                .filter_by(estado="completada")
                .scalar()
            )
            stats["total_completadas"] = (
                float(total_completadas) if total_completadas else 0.0
            )

            return stats
        except SQLAlchemyError as exc:
            logger.error("Error al obtener estadísticas de órdenes: %s", exc)
            return {}

    @staticmethod
    def search_orders(
        search: Optional[str] = None,
        estado: Optional[str] = None,
        fecha_inicio: Optional[str] = None,
        fecha_fin: Optional[str] = None,
        page: int = 1,
        per_page: int = 12,
    ) -> Tuple[List[Orden], int, Optional[str]]:
        """
        Busca órdenes con filtros y paginación.

        Returns:
            Tuple[List[Orden], int, Optional[str]]
            (órdenes, total_páginas, error)
        """
        try:
            from datetime import datetime

            # Asegurar valores válidos
            page = max(1, page)
            per_page = max(1, per_page)

            query = Orden.query.options(joinedload(Orden.usuario))

            # Estado
            if estado:
                if estado not in ESTADOS_VALIDOS:
                    return [], 0, f"Estado '{estado}' no válido"

                query = query.filter(Orden.estado == estado)

            # Fechas
            try:
                if fecha_inicio:
                    inicio_dt = datetime.strptime(
                        fecha_inicio,
                        "%Y-%m-%d",
                    )

                    query = query.filter(Orden.fecha_creacion >= inicio_dt)

                if fecha_fin:
                    fin_dt = datetime.strptime(
                        fecha_fin,
                        "%Y-%m-%d",
                    ).replace(
                        hour=23,
                        minute=59,
                        second=59,
                        microsecond=999999,
                    )

                    query = query.filter(Orden.fecha_creacion <= fin_dt)

            except ValueError:
                return [], 0, "Formato de fecha inválido (YYYY-MM-DD)"

            # Búsqueda
            if search and search.strip():
                query = query.outerjoin(Orden.detalles).outerjoin(Orden.usuario)

                bloques = [
                    bloque.strip() for bloque in search.split("+") if bloque.strip()
                ]

                condiciones = []

                for bloque in bloques:
                    prefijo = None
                    valor = bloque

                    if ":" in bloque:
                        prefijo, valor = bloque.split(":", 1)

                        prefijo = prefijo.lower().strip()
                        valor = valor.strip()

                    termino = f"%{valor}%"

                    # búsqueda especializada
                    if prefijo == "sku":
                        condicion = OrdenDetalle.clave_producto.ilike(termino)

                    elif prefijo == "prod":
                        condicion = OrdenDetalle.producto.ilike(termino)

                    elif prefijo == "comp":
                        condicion = Orden.comprador.ilike(termino)

                    elif prefijo == "ord":
                        condicion = Orden.clave_orden.ilike(termino)

                    elif prefijo == "vend":
                        condicion = db.or_(
                            Usuario.nombre.ilike(termino),
                            Usuario.ap_paterno.ilike(termino),
                        )

                    else:
                        condicion = db.or_(
                            Orden.clave_orden.ilike(termino),
                            Orden.comprador.ilike(termino),
                            OrdenDetalle.producto.ilike(termino),
                            OrdenDetalle.clave_producto.ilike(termino),
                            Usuario.nombre.ilike(termino),
                            Usuario.ap_paterno.ilike(termino),
                        )

                    condiciones.append(condicion)

                query = query.filter(db.and_(*condiciones)).distinct()

            # Orden estable
            query = query.order_by(
                Orden.fecha_creacion.desc(),
                Orden.id_orden.desc(),
            )

            # Paginación
            paginated = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False,
            )

            if paginated.total == 0:
                total_pages = 1
                actual_page = 1
                items = paginated.items
            else:
                total_pages = paginated.pages
                actual_page = page

                if page > total_pages:
                    actual_page = total_pages
                    paginated = query.paginate(
                        page=actual_page,
                        per_page=per_page,
                        error_out=False,
                    )

                items = paginated.items

            return (
                items,
                total_pages,
                None,
            )

        except SQLAlchemyError as exc:
            logger.exception(f"Error en búsqueda de órdenes: {exc}")

            return (
                [],
                0,
                "Error de base de datos al buscar órdenes",
            )

    @staticmethod
    def _validate_informacion_adicional(
        tipo_cotizacion: str | None,
        departamento: str | None = None,
        no_solicitud: str | None = None,
        proveedor_unam: str | None = None,
        punto_entrega: str | None = None,
    ) -> tuple[dict, str | None]:
        """
        Valida y construye el contenido de informacion_adicional.

        OTROS:
            {}

        UNAM:
            {
                "departamento":"",
                "no_solicitud": "",
                "proveedor_unam": ""
            }
        """

        tipo = (tipo_cotizacion or "OTROS").strip().upper()

        if tipo not in TIPOS_COTIZACION:
            return {}, (
                f"Tipo de cotización '{tipo}' no válido. "
                f"Opciones: {sorted(TIPOS_COTIZACION)}"
            )

        if tipo == "OTROS":
            return {}, None

        return {
            "departamento": str(departamento or "").strip(),
            "no_solicitud": str(no_solicitud or "").strip(),
            "proveedor_unam": str(proveedor_unam or "").strip(),
            "punto_entrega": str(punto_entrega or "").strip(),
        }, None

    @staticmethod
    def _generar_clave_unam(prefijo: str, clave_actual: str | None = None) -> str:
        base = f"UM{prefijo}{datetime.now().strftime('%y')}"

        if clave_actual and clave_actual.startswith(base):
            return clave_actual

        ultima = (
            Orden.query.filter(Orden.clave_orden.like(f"{base}%"))
            .order_by(Orden.clave_orden.desc())
            .first()
        )

        if ultima:
            consecutivo = int(ultima.clave_orden[len(base) :]) + 1
        else:
            consecutivo = 1

        return f"{base}{consecutivo:03d}"
