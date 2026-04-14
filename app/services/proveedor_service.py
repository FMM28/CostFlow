from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.proveedor import Proveedor

logger = logging.getLogger(__name__)


class ProveedorService:

    @staticmethod
    def get_all(include_deleted: bool = False) -> List[Proveedor]:
        """
        Retorna todos los proveedores ordenados por nombre.

        Args:
            include_deleted: Si es True incluye registros con soft delete.
        
        Returns:
            List[Proveedor]: Lista de proveedores (vacía si hay error).
        """
        try:
            query = Proveedor.query
            if not include_deleted:
                query = query.filter(Proveedor.deleted_at.is_(None))
            return query.order_by(Proveedor.nombre).all()
        except SQLAlchemyError as exc:
            logger.error("Error al obtener proveedores: %s", exc)
            return []

    @staticmethod
    def get_by_id(id_proveedor: int, include_deleted: bool = False) -> Optional[Proveedor]:
        """
        Retorna un proveedor por su PK.

        Returns:
            Optional[Proveedor]: Proveedor encontrado o None si no existe/hay error.
        """
        try:
            proveedor = db.session.get(Proveedor, id_proveedor)
        except SQLAlchemyError as exc:
            logger.error("Error al buscar proveedor id=%s: %s", id_proveedor, exc)
            return None

        if proveedor is None:
            logger.warning("Proveedor con id %s no encontrado", id_proveedor)
            return None
        
        if not include_deleted and proveedor.deleted_at is not None:
            logger.warning("Proveedor con id %s ha sido eliminado", id_proveedor)
            return None
        
        return proveedor

    @staticmethod
    def search_by_nombre(nombre: str, include_deleted: bool = False) -> List[Proveedor]:
        """
        Busca proveedores cuyo nombre contenga la cadena indicada (case-insensitive).
        
        Returns:
            List[Proveedor]: Lista de proveedores encontrados (vacía si no hay resultados o error).
        """
        if not nombre or not nombre.strip():
            logger.warning("Término de búsqueda vacío")
            return []
        
        try:
            query = Proveedor.query.filter(
                Proveedor.nombre.ilike(f"%{nombre.strip()}%")
            )
            if not include_deleted:
                query = query.filter(Proveedor.deleted_at.is_(None))
            return query.order_by(Proveedor.nombre).all()
        except SQLAlchemyError as exc:
            logger.error("Error al buscar proveedores por nombre='%s': %s", nombre, exc)
            return []

    @staticmethod
    def create(data: dict) -> Tuple[Optional[Proveedor], Optional[str]]:
        """
        Crea un nuevo proveedor.

        Campos requeridos: nombre.
        
        Returns:
            Tuple[Optional[Proveedor], Optional[str]]: (proveedor_creado, mensaje_error)
        """
        nombre = str(data.get("nombre", "")).strip()
        if not nombre:
            return None, "El campo 'nombre' es obligatorio"
        
        if len(nombre) > 100:  # Asumiendo límite en el modelo
            return None, "El nombre no puede exceder 100 caracteres"

        proveedor = Proveedor(nombre=nombre)

        try:
            db.session.add(proveedor)
            db.session.commit()
            logger.info("Proveedor creado: id=%s nombre='%s'", proveedor.id_proveedor, nombre)
            return proveedor, None
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning("IntegrityError al crear proveedor nombre='%s': %s", nombre, exc)
            return None, f"Ya existe un proveedor con el nombre '{nombre}'"
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al crear proveedor: %s", exc)
            return None, "Error de base de datos al crear el proveedor"

    @staticmethod
    def update(id_proveedor: int, data: dict) -> Tuple[Optional[Proveedor], Optional[str]]:
        """
        Actualiza el nombre de un proveedor activo.

        Returns:
            Tuple[Optional[Proveedor], Optional[str]]: (proveedor_actualizado, mensaje_error)
        """
        if not data:
            return None, "No se proporcionaron campos para actualizar"

        proveedor = ProveedorService.get_by_id(id_proveedor)
        if proveedor is None:
            return None, f"Proveedor con id {id_proveedor} no encontrado o eliminado"

        if "nombre" in data:
            nuevo_nombre = str(data["nombre"]).strip()
            if not nuevo_nombre:
                return None, "El campo 'nombre' no puede estar vacío"
            if len(nuevo_nombre) > 100:
                return None, "El nombre no puede exceder 100 caracteres"
            proveedor.nombre = nuevo_nombre

        try:
            db.session.commit()
            logger.info("Proveedor actualizado: id=%s", id_proveedor)
            return proveedor, None
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning("IntegrityError al actualizar proveedor id=%s: %s", id_proveedor, exc)
            return None, f"Ya existe un proveedor con el nombre '{data.get('nombre')}'"
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al actualizar proveedor id=%s: %s", id_proveedor, exc)
            return None, "Error de base de datos al actualizar el proveedor"

    @staticmethod
    def soft_delete(id_proveedor: int) -> Tuple[bool, Optional[str]]:
        """
        Marca el proveedor como eliminado sin borrarlo de la base de datos.

        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        proveedor = ProveedorService.get_by_id(id_proveedor)
        if proveedor is None:
            return False, f"Proveedor con id {id_proveedor} no encontrado o ya eliminado"

        try:
            proveedor.deleted_at = datetime.now(tz=timezone.utc)
            db.session.commit()
            logger.info("Proveedor eliminado (soft): id=%s", id_proveedor)
            return True, None
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al hacer soft delete de proveedor id=%s: %s", id_proveedor, exc)
            return False, "Error de base de datos al eliminar el proveedor"

    @staticmethod
    def restore(id_proveedor: int) -> Tuple[bool, Optional[str]]:
        """
        Restaura un proveedor que fue eliminado con soft delete.

        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        proveedor = ProveedorService.get_by_id(id_proveedor, include_deleted=True)
        if proveedor is None:
            return False, f"Proveedor con id {id_proveedor} no encontrado"

        if proveedor.deleted_at is None:
            return False, f"El proveedor con id {id_proveedor} no está eliminado"

        try:
            proveedor.deleted_at = None
            db.session.commit()
            logger.info("Proveedor restaurado: id=%s", id_proveedor)
            return True, None
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al restaurar proveedor id=%s: %s", id_proveedor, exc)
            return False, "Error de base de datos al restaurar el proveedor"

    @staticmethod
    def hard_delete(id_proveedor: int) -> Tuple[bool, Optional[str]]:
        """
        Elimina permanentemente el proveedor de la base de datos.

        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        proveedor = ProveedorService.get_by_id(id_proveedor, include_deleted=True)
        if proveedor is None:
            return False, f"Proveedor con id {id_proveedor} no encontrado"

        try:
            db.session.delete(proveedor)
            db.session.commit()
            logger.info("Proveedor eliminado permanentemente: id=%s", id_proveedor)
            return True, None
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning(
                "IntegrityError al eliminar proveedor id=%s (tiene detalles asociados): %s",
                id_proveedor, exc
            )
            return False, (
                f"No se puede eliminar el proveedor {id_proveedor} "
                "porque tiene órdenes asociadas. Utiliza soft_delete en su lugar."
            )
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.error("Error al eliminar proveedor id=%s: %s", id_proveedor, exc)
            return False, "Error de base de datos al eliminar el proveedor"
