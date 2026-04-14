from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Tuple, Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.orden import Orden
from app.models.orden_detalle import OrdenDetalle

logger = logging.getLogger(__name__)

_CAMPOS_NUMERICOS = frozenset(
    {"precio_unitario", "ganancia_unitaria", "costo_envio", "cantidad"}
)


class OrdenDetalleService:

    @staticmethod
    def get_by_orden(id_orden: int) -> List[OrdenDetalle]:
        """Retorna todos los detalles de una orden dada."""
        try:
            return OrdenDetalle.query.filter_by(id_orden=id_orden).all()
        except SQLAlchemyError as exc:
            logger.error("Error al obtener detalles de orden id=%s: %s", id_orden, exc)
            return []

    @staticmethod
    def get_by_id(id_detalle: int) -> Optional[OrdenDetalle]:
        """Retorna un detalle por su PK o None si no existe."""
        try:
            return db.session.get(OrdenDetalle, id_detalle)
        except SQLAlchemyError as exc:
            logger.error("Error al buscar detalle id=%s: %s", id_detalle, exc)
            return None

    @staticmethod
    def _to_decimal(value: Any, campo: str) -> Optional[Decimal]:
        """Convierte un valor a Decimal o retorna None si es inválido."""
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            logger.warning("Valor inválido para '%s': %r", campo, value)
            return None

    @staticmethod
    def _calcular_campos(data: dict) -> Optional[dict]:
        """
        Deriva precio_venta y subtotal a partir de los campos numéricos del detalle.
        
        Returns:
            Dict con campos calculados o None si hay error de validación.
        """
        # Validar precio_unitario (requerido)
        precio_unitario = OrdenDetalleService._to_decimal(
            data.get("precio_unitario", 0), "precio_unitario"
        )
        if precio_unitario is None or precio_unitario < 0:
            logger.warning("precio_unitario inválido o negativo: %r", data.get("precio_unitario"))
            return None

        # Validar ganancia_unitaria (opcional, default 0)
        ganancia_unitaria = OrdenDetalleService._to_decimal(
            data.get("ganancia_unitaria", 0), "ganancia_unitaria"
        )
        if ganancia_unitaria is None or ganancia_unitaria < 0:
            logger.warning("ganancia_unitaria inválida o negativa: %r", data.get("ganancia_unitaria"))
            return None

        # Validar costo_envio (opcional, default 0)
        costo_envio = OrdenDetalleService._to_decimal(
            data.get("costo_envio", 0), "costo_envio"
        )
        if costo_envio is None or costo_envio < 0:
            logger.warning("costo_envio inválido o negativo: %r", data.get("costo_envio"))
            return None

        # Validar cantidad (requerido)
        try:
            cantidad = int(data.get("cantidad", 0))
            if cantidad <= 0:
                logger.warning("cantidad debe ser > 0: %r", data.get("cantidad"))
                return None
        except (TypeError, ValueError):
            logger.warning("cantidad no es un entero válido: %r", data.get("cantidad"))
            return None

        # Calcular campos derivados
        precio_venta = precio_unitario + ganancia_unitaria
        subtotal = precio_venta * cantidad

        return {
            "precio_unitario": precio_unitario,
            "ganancia_unitaria": ganancia_unitaria,
            "costo_envio": costo_envio,
            "precio_venta": precio_venta,
            "subtotal": subtotal,
            "cantidad": cantidad,
        }

    @staticmethod
    def _sync_total_orden(id_orden: int) -> bool:
        """
        Actualiza el campo 'total' de la orden sumando los subtotales de sus detalles.
        
        Returns:
            True si se actualizó correctamente, False si hubo error.
        """
        try:
            orden = db.session.get(Orden, id_orden)
            if orden is None:
                logger.warning("Orden id=%s no encontrada para sincronizar total", id_orden)
                return False

            suma = db.session.query(db.func.sum(OrdenDetalle.subtotal)).filter_by(
                id_orden=id_orden
            ).scalar()
            
            orden.total = suma if suma is not None else Decimal("0.00")
            return True
        except SQLAlchemyError as exc:
            logger.error("Error al sincronizar total de orden id=%s: %s", id_orden, exc)
            return False

    @staticmethod
    def _validate_data_requerida(data: dict) -> Optional[str]:
        """
        Valida que los campos mínimos requeridos estén presentes.
        
        Returns:
            Mensaje de error o None si es válido.
        """
        campos_requeridos = ["producto", "cantidad", "precio_unitario"]
        
        for campo in campos_requeridos:
            if campo not in data or data[campo] is None:
                return f"El campo '{campo}' es obligatorio"
        
        producto = str(data.get("producto", "")).strip()
        if not producto:
            return "El campo 'producto' no puede estar vacío"
        
        return None

    @staticmethod
    def add_detalle(id_orden: int, data: dict) -> Tuple[Optional[OrdenDetalle], Optional[str]]:
        """
        Agrega un detalle a una orden existente y sincroniza su total.
        
        Returns:
            Tuple[Optional[OrdenDetalle], Optional[str]]: (detalle_creado, mensaje_error)
        """
        # Validar datos requeridos
        error = OrdenDetalleService._validate_data_requerida(data)
        if error:
            return None, error

        # Verificar que la orden existe
        try:
            orden = db.session.get(Orden, id_orden)
            if orden is None:
                return None, f"Orden con id {id_orden} no encontrada"
        except SQLAlchemyError as exc:
            logger.error("Error al verificar orden id=%s: %s", id_orden, exc)
            return None, "Error de base de datos al verificar la orden"

        # Calcular campos numéricos
        calculados = OrdenDetalleService._calcular_campos(data)
        if calculados is None:
            return None, "Error en los campos numéricos del detalle"

        # Crear detalle
        detalle = OrdenDetalle(
            id_orden=id_orden,
            id_proveedor=data.get("id_proveedor"),
            producto=str(data["producto"]).strip(),
            clave_producto=data.get("clave_producto"),
            url_producto=data.get("url_producto"),
            url_imagen=data.get("url_imagen"),
            **calculados,
        )

        try:
            db.session.add(detalle)
            
            # Sincronizar total de la orden
            if not OrdenDetalleService._sync_total_orden(id_orden):
                db.session.rollback()
                return None, "Error al actualizar el total de la orden"
            
            db.session.commit()
            logger.info(
                "Detalle agregado: id=%s orden=%s producto='%s'",
                detalle.id_detalle, id_orden, detalle.producto
            )
            return detalle, None
            
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning("IntegrityError al agregar detalle a orden id=%s: %s", id_orden, exc)
            return None, "Conflicto de integridad al agregar el detalle"
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al agregar detalle a orden id=%s: %s", id_orden, exc)
            return None, "Error de base de datos al agregar el detalle"

    @staticmethod
    def add_bulk(id_orden: int, items: List[dict]) -> Tuple[List[OrdenDetalle], Optional[str]]:
        """
        Agrega múltiples detalles a una orden en una sola transacción atómica.
        
        Returns:
            Tuple[List[OrdenDetalle], Optional[str]]: (detalles_creados, mensaje_error)
        """
        if not items:
            return [], "La lista de ítems no puede estar vacía"

        # Verificar que la orden existe
        try:
            orden = db.session.get(Orden, id_orden)
            if orden is None:
                return [], f"Orden con id {id_orden} no encontrada"
        except SQLAlchemyError as exc:
            logger.error("Error al verificar orden id=%s: %s", id_orden, exc)
            return [], "Error de base de datos al verificar la orden"

        # Validar todos los ítems antes de persistir
        detalles = []
        for idx, item in enumerate(items):
            # Validar datos requeridos
            error = OrdenDetalleService._validate_data_requerida(item)
            if error:
                return [], f"Error en ítem #{idx + 1}: {error}"

            # Calcular campos numéricos
            calculados = OrdenDetalleService._calcular_campos(item)
            if calculados is None:
                return [], f"Error en campos numéricos del ítem #{idx + 1}"

            detalle = OrdenDetalle(
                id_orden=id_orden,
                id_proveedor=item.get("id_proveedor"),
                producto=str(item["producto"]).strip(),
                clave_producto=item.get("clave_producto"),
                url_producto=item.get("url_producto"),
                url_imagen=item.get("url_imagen"),
                **calculados,
            )
            db.session.add(detalle)
            detalles.append(detalle)

        try:
            # Sincronizar total de la orden
            if not OrdenDetalleService._sync_total_orden(id_orden):
                db.session.rollback()
                return [], "Error al actualizar el total de la orden"
            
            db.session.commit()
            logger.info("%d detalle(s) agregados en bulk a orden id=%s", len(detalles), id_orden)
            return detalles, None
            
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning("IntegrityError en bulk insert para orden id=%s: %s", id_orden, exc)
            return [], "Conflicto de integridad en la inserción masiva"
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error en bulk insert para orden id=%s: %s", id_orden, exc)
            return [], "Error de base de datos en la inserción masiva"

    @staticmethod
    def update_detalle(id_detalle: int, data: dict) -> Tuple[Optional[OrdenDetalle], Optional[str]]:
        """
        Actualiza campos de un detalle existente y sincroniza el total de su orden.
        
        Returns:
            Tuple[Optional[OrdenDetalle], Optional[str]]: (detalle_actualizado, mensaje_error)
        """
        if not data:
            return None, "No se proporcionaron campos para actualizar"

        # Obtener detalle
        detalle = OrdenDetalleService.get_by_id(id_detalle)
        if detalle is None:
            return None, f"Detalle con id {id_detalle} no encontrado"

        # Actualizar campos simples
        campos_simples = ["id_proveedor", "producto", "clave_producto", "url_producto", "url_imagen"]
        for field in campos_simples:
            if field in data:
                if field == "producto":
                    producto = str(data[field]).strip()
                    if not producto:
                        return None, "El campo 'producto' no puede estar vacío"
                    setattr(detalle, field, producto)
                else:
                    setattr(detalle, field, data[field])

        # Recalcular si hay campos numéricos
        if _CAMPOS_NUMERICOS & data.keys():
            merged = {
                "precio_unitario": detalle.precio_unitario,
                "ganancia_unitaria": detalle.ganancia_unitaria,
                "costo_envio": detalle.costo_envio,
                "cantidad": detalle.cantidad,
                **{k: v for k, v in data.items() if k in _CAMPOS_NUMERICOS},
            }
            
            calculados = OrdenDetalleService._calcular_campos(merged)
            if calculados is None:
                return None, "Error en los campos numéricos para actualizar"
            
            for campo, valor in calculados.items():
                setattr(detalle, campo, valor)

        try:
            # Sincronizar total de la orden
            if not OrdenDetalleService._sync_total_orden(detalle.id_orden):
                db.session.rollback()
                return None, "Error al actualizar el total de la orden"
            
            db.session.commit()
            logger.info("Detalle actualizado: id=%s", id_detalle)
            return detalle, None
            
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning("IntegrityError al actualizar detalle id=%s: %s", id_detalle, exc)
            return None, "Conflicto de integridad al actualizar el detalle"
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al actualizar detalle id=%s: %s", id_detalle, exc)
            return None, "Error de base de datos al actualizar el detalle"

    @staticmethod
    def delete_detalle(id_detalle: int) -> Tuple[bool, Optional[str]]:
        """
        Elimina un detalle y sincroniza el total de su orden.
        
        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        detalle = OrdenDetalleService.get_by_id(id_detalle)
        if detalle is None:
            return False, f"Detalle con id {id_detalle} no encontrado"

        id_orden = detalle.id_orden

        try:
            db.session.delete(detalle)
            
            # Sincronizar total de la orden
            if not OrdenDetalleService._sync_total_orden(id_orden):
                db.session.rollback()
                return False, "Error al actualizar el total de la orden"
            
            db.session.commit()
            logger.info("Detalle eliminado: id=%s (orden=%s)", id_detalle, id_orden)
            return True, None
            
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning("IntegrityError al eliminar detalle id=%s: %s", id_detalle, exc)
            return False, "No se puede eliminar el detalle por restricciones de integridad"
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al eliminar detalle id=%s: %s", id_detalle, exc)
            return False, "Error de base de datos al eliminar el detalle"

    @staticmethod
    def delete_by_orden(id_orden: int) -> Tuple[int, Optional[str]]:
        """
        Elimina todos los detalles de una orden y pone su total en 0.
        
        Returns:
            Tuple[int, Optional[str]]: (cantidad_eliminada, mensaje_error)
        """
        try:
            count = OrdenDetalle.query.filter_by(id_orden=id_orden).delete(
                synchronize_session="fetch"
            )
            
            # Sincronizar total de la orden
            if not OrdenDetalleService._sync_total_orden(id_orden):
                db.session.rollback()
                return 0, "Error al actualizar el total de la orden"
            
            db.session.commit()
            logger.info("%d detalle(s) eliminados de orden id=%s", count, id_orden)
            return count, None
            
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al eliminar detalles de orden id=%s: %s", id_orden, exc)
            return 0, f"Error de base de datos al eliminar los detalles de la orden {id_orden}"