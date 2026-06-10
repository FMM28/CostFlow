from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.orden import Orden
from app.models.orden_detalle import OrdenDetalle

logger = logging.getLogger(__name__)

_CAMPOS_NUMERICOS = frozenset(
    {
        "precio_unitario",
        "costo_envio",
        "cantidad",
        "margen_ganancia",
    }
)

_DECIMAL_2 = Decimal("0.01")
_DECIMAL_100 = Decimal("100")


class OrdenDetalleService:

    @staticmethod
    def get_by_orden(id_orden: int) -> List[OrdenDetalle]:
        try:
            return (
                OrdenDetalle.query
                .filter_by(id_orden=id_orden)
                .order_by(OrdenDetalle.id_detalle.asc())
                .all()
            )
        except SQLAlchemyError as exc:
            logger.error(
                "Error al obtener detalles de orden %s: %s",
                id_orden,
                exc,
            )
            return []

    @staticmethod
    def get_by_id(id_detalle: int) -> Optional[OrdenDetalle]:
        try:
            return db.session.get(OrdenDetalle, id_detalle)
        except SQLAlchemyError as exc:
            logger.error(
                "Error al obtener detalle %s: %s",
                id_detalle,
                exc,
            )
            return None

    @staticmethod
    def _to_decimal(value: Any, campo: str) -> Optional[Decimal]:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            logger.warning(
                "Valor inválido para %s: %r",
                campo,
                value,
            )
            return None

    @staticmethod
    def _round(value: Decimal) -> Decimal:
        return value.quantize(
            _DECIMAL_2,
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def _validate_data_requerida(data: dict) -> Optional[str]:

        campos_requeridos = (
            "producto",
            "cantidad",
            "precio_unitario",
            "margen_ganancia",
        )

        for campo in campos_requeridos:
            if campo not in data:
                return f"El campo '{campo}' es obligatorio"

            if data[campo] is None:
                return f"El campo '{campo}' es obligatorio"

        producto = str(data.get("producto", "")).strip()

        if not producto:
            return "El campo 'producto' no puede estar vacío"

        return None

    @staticmethod
    def _calcular_campos(data: dict) -> Optional[dict]:

        precio_unitario = OrdenDetalleService._to_decimal(
            data.get("precio_unitario"),
            "precio_unitario",
        )

        if precio_unitario is None or precio_unitario < 0:
            logger.warning(
                "precio_unitario inválido: %r",
                data.get("precio_unitario"),
            )
            return None

        costo_envio = OrdenDetalleService._to_decimal(
            data.get("costo_envio", 0),
            "costo_envio",
        )

        if costo_envio is None or costo_envio < 0:
            logger.warning(
                "costo_envio inválido: %r",
                data.get("costo_envio"),
            )
            return None

        margen_ganancia = OrdenDetalleService._to_decimal(
            data.get("margen_ganancia"),
            "margen_ganancia",
        )

        if margen_ganancia is None:
            logger.warning(
                "margen_ganancia inválido: %r",
                data.get("margen_ganancia"),
            )
            return None

        if margen_ganancia < 0 or margen_ganancia >= 100:
            logger.warning(
                "margen_ganancia fuera de rango: %s",
                margen_ganancia,
            )
            return None

        try:
            cantidad = int(data.get("cantidad"))
        except (TypeError, ValueError):
            logger.warning(
                "cantidad inválida: %r",
                data.get("cantidad"),
            )
            return None

        if cantidad <= 0:
            logger.warning(
                "cantidad debe ser mayor a cero: %s",
                cantidad,
            )
            return None

        divisor = Decimal("1") - (
            margen_ganancia / _DECIMAL_100
        )

        if divisor <= 0:
            logger.warning(
                "Divisor inválido para margen %s",
                margen_ganancia,
            )
            return None

        precio_producto_con_margen = (
            precio_unitario / divisor
        )

        precio_venta = OrdenDetalleService._round(
            precio_producto_con_margen + costo_envio
        )

        ganancia_unitaria = OrdenDetalleService._round(
            precio_producto_con_margen - precio_unitario
        )

        subtotal = OrdenDetalleService._round(
            precio_venta * cantidad
        )

        return {
            "precio_unitario": OrdenDetalleService._round(precio_unitario),
            "costo_envio": OrdenDetalleService._round(costo_envio),
            "margen_ganancia": OrdenDetalleService._round(margen_ganancia),
            "ganancia_unitaria": ganancia_unitaria,
            "precio_venta": precio_venta,
            "subtotal": subtotal,
            "cantidad": cantidad,
        }

    @staticmethod
    def _sync_total_orden(id_orden: int) -> bool:

        try:

            db.session.flush()

            orden = db.session.get(Orden, id_orden)

            if orden is None:
                logger.warning(
                    "Orden %s no encontrada",
                    id_orden,
                )
                return False

            total = (
                db.session.query(
                    db.func.coalesce(
                        db.func.sum(OrdenDetalle.subtotal),
                        0,
                    )
                )
                .filter(
                    OrdenDetalle.id_orden == id_orden
                )
                .scalar()
            )

            orden.total = OrdenDetalleService._round(
                Decimal(str(total))
            )

            return True

        except SQLAlchemyError as exc:
            logger.error(
                "Error al sincronizar total de orden %s: %s",
                id_orden,
                exc,
            )
            return False

    @staticmethod
    def add_detalle(
        id_orden: int,
        data: dict,
    ) -> Tuple[Optional[OrdenDetalle], Optional[str]]:

        error = OrdenDetalleService._validate_data_requerida(data)

        if error:
            return None, error

        try:

            orden = db.session.get(Orden, id_orden)

            if orden is None:
                return None, "La orden no existe"

            calculados = OrdenDetalleService._calcular_campos(data)

            if calculados is None:
                return None, "Datos numéricos inválidos"

            detalle = OrdenDetalle(
                id_orden=id_orden,
                id_proveedor=data.get("id_proveedor"),
                producto=str(data["producto"]).strip(),
                clave_producto=data.get("clave_producto"),
                url_producto=data.get("url_producto"),
                url_imagen=data.get("url_imagen"),
                **calculados,
            )

            db.session.add(detalle)

            if not OrdenDetalleService._sync_total_orden(id_orden):
                db.session.rollback()
                return None, "No fue posible actualizar el total de la orden"

            db.session.commit()

            logger.info(
                "Detalle creado id=%s orden=%s",
                detalle.id_detalle,
                id_orden,
            )

            return detalle, None

        except IntegrityError as exc:
            db.session.rollback()
            logger.warning(
                "IntegrityError creando detalle: %s",
                exc,
            )
            return None, "Error de integridad"

        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error(
                "Error creando detalle: %s",
                exc,
            )
            return None, "Error de base de datos"

    @staticmethod
    def add_bulk(
        id_orden: int,
        items: List[dict],
    ) -> Tuple[List[OrdenDetalle], Optional[str]]:

        if not items:
            return [], "No se recibieron productos"

        try:

            orden = db.session.get(Orden, id_orden)

            if orden is None:
                return [], "La orden no existe"

            detalles = []

            for idx, item in enumerate(items, start=1):

                error = OrdenDetalleService._validate_data_requerida(item)

                if error:
                    return [], f"Ítem #{idx}: {error}"

                calculados = OrdenDetalleService._calcular_campos(item)

                if calculados is None:
                    return [], f"Ítem #{idx}: datos inválidos"

                detalle = OrdenDetalle(
                    id_orden=id_orden,
                    id_proveedor=item.get("id_proveedor"),
                    producto=str(item["producto"]).strip(),
                    clave_producto=item.get("clave_producto"),
                    url_producto=item.get("url_producto"),
                    url_imagen=item.get("url_imagen"),
                    **calculados,
                )

                detalles.append(detalle)
                db.session.add(detalle)

            if not OrdenDetalleService._sync_total_orden(id_orden):
                db.session.rollback()
                return [], "No fue posible actualizar el total de la orden"

            db.session.commit()

            logger.info(
                "%s detalles agregados a orden %s",
                len(detalles),
                id_orden,
            )

            return detalles, None

        except IntegrityError as exc:
            db.session.rollback()
            logger.warning(
                "IntegrityError en inserción masiva: %s",
                exc,
            )
            return [], "Error de integridad"

        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error(
                "Error en inserción masiva: %s",
                exc,
            )
            return [], "Error de base de datos"

    @staticmethod
    def update_detalle(
        id_detalle: int,
        data: dict,
    ) -> Tuple[Optional[OrdenDetalle], Optional[str]]:

        if not data:
            return None, "No se recibieron datos"

        detalle = OrdenDetalleService.get_by_id(id_detalle)

        if detalle is None:
            return None, "Detalle no encontrado"

        campos_simples = (
            "id_proveedor",
            "producto",
            "clave_producto",
            "url_producto",
            "url_imagen",
        )

        for campo in campos_simples:

            if campo not in data:
                continue

            if campo == "producto":
                valor = str(data[campo]).strip()

                if not valor:
                    return None, "El producto no puede estar vacío"

                detalle.producto = valor

            else:
                setattr(
                    detalle,
                    campo,
                    data[campo],
                )

        if _CAMPOS_NUMERICOS & data.keys():

            merged = {
                "precio_unitario": detalle.precio_unitario,
                "costo_envio": detalle.costo_envio,
                "cantidad": detalle.cantidad,
                "margen_ganancia": detalle.margen_ganancia,
                **{
                    k: v
                    for k, v in data.items()
                    if k in _CAMPOS_NUMERICOS
                },
            }

            calculados = OrdenDetalleService._calcular_campos(
                merged
            )

            if calculados is None:
                return None, "Datos numéricos inválidos"

            for campo, valor in calculados.items():
                setattr(
                    detalle,
                    campo,
                    valor,
                )

        try:

            if not OrdenDetalleService._sync_total_orden(
                detalle.id_orden
            ):
                db.session.rollback()
                return None, "No fue posible actualizar el total"

            db.session.commit()

            logger.info(
                "Detalle actualizado id=%s",
                id_detalle,
            )

            return detalle, None

        except IntegrityError as exc:
            db.session.rollback()
            logger.warning(
                "IntegrityError actualizando detalle %s: %s",
                id_detalle,
                exc,
            )
            return None, "Error de integridad"

        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error(
                "Error actualizando detalle %s: %s",
                id_detalle,
                exc,
            )
            return None, "Error de base de datos"

    @staticmethod
    def delete_detalle(
        id_detalle: int,
    ) -> Tuple[bool, Optional[str]]:

        detalle = OrdenDetalleService.get_by_id(id_detalle)

        if detalle is None:
            return False, "Detalle no encontrado"

        id_orden = detalle.id_orden

        try:

            db.session.delete(detalle)

            if not OrdenDetalleService._sync_total_orden(id_orden):
                db.session.rollback()
                return False, "No fue posible actualizar el total"

            db.session.commit()

            logger.info(
                "Detalle eliminado id=%s",
                id_detalle,
            )

            return True, None

        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error(
                "Error eliminando detalle %s: %s",
                id_detalle,
                exc,
            )
            return False, "Error de base de datos"

    @staticmethod
    def delete_by_orden(
        id_orden: int,
    ) -> Tuple[int, Optional[str]]:

        try:

            cantidad = (
                OrdenDetalle.query
                .filter_by(id_orden=id_orden)
                .delete(
                    synchronize_session=False
                )
            )

            if not OrdenDetalleService._sync_total_orden(id_orden):
                db.session.rollback()
                return 0, "No fue posible actualizar el total"

            db.session.commit()

            logger.info(
                "%s detalles eliminados de orden %s",
                cantidad,
                id_orden,
            )

            return cantidad, None

        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error(
                "Error eliminando detalles de orden %s: %s",
                id_orden,
                exc,
            )
            return 0, "Error de base de datos"