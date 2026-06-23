from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Tuple

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.orden import Orden
from app.models.orden_detalle import OrdenDetalle

from datetime import datetime

logger = logging.getLogger(__name__)

ESTADOS_VALIDOS = frozenset({"pendiente", "aprobada", "completada", "cancelada"})


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
        clave = str(data.get("clave_orden", "")).strip()
        if not clave:
            return "El campo 'clave_orden' es obligatorio"

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

        clave = str(data["clave_orden"]).strip()
        estado = data.get("estado", "pendiente")
        comprador = str(data["comprador"]).strip()
        total = OrdenService._to_decimal(data.get("total", "0.00"))

        # Verificar unicidad de clave
        try:
            duplicado = Orden.query.filter_by(clave_orden=clave).first()
            if duplicado:
                return None, f"Ya existe una orden con la clave '{clave}'"
        except SQLAlchemyError as exc:
            logger.error(
                "Error al verificar duplicado de clave_orden='%s': %s", clave, exc
            )
            return None, "Error de base de datos al verificar la orden"

        # Crear orden
        try:
            orden = Orden(
                clave_orden=clave,
                id_usuario=int(data["id_usuario"]),
                comprador=comprador,
                estado=estado,
                total=total,
            )

            db.session.add(orden)
            db.session.commit()
            logger.info(
                "Orden creada: id=%s clave='%s'", orden.id_orden, orden.clave_orden
            )
            return orden, None

        except IntegrityError as exc:
            db.session.rollback()
            logger.warning("IntegrityError al crear orden clave='%s': %s", clave, exc)
            return None, f"Ya existe una orden con la clave '{clave}'"
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al crear orden clave='%s': %s", clave, exc)
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
            if not nueva_clave:
                return None, "La 'clave_orden' no puede estar vacía"

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
                termino = f"%{search.strip()}%"

                query = query.filter(
                    db.or_(
                        Orden.clave_orden.ilike(termino),
                        Orden.comprador.ilike(termino),
                    )
                )

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
