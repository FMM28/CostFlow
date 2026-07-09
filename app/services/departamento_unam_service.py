from app.extensions import db
from app.models.departamento_unam import DepartamentoUNAM
import logging
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from typing import Optional, List, Any
from sqlalchemy.orm import Query

logger = logging.getLogger(__name__)


class DepartamentoUNAMService:
    @staticmethod
    def get_all() -> List[DepartamentoUNAM]:
        """
        Obtiene todos los departamentos ordenados por nombre.

        Returns:
            List[DepartamentoUNAM]: Lista de todos los departamentos
        """
        try:
            return DepartamentoUNAM.query.order_by(DepartamentoUNAM.nombre.asc()).all()
        except SQLAlchemyError as e:
            logger.error(f"Error al obtener todos los departamentos: {str(e)}")
            raise RuntimeError("Error al consultar los departamentos") from e

    @staticmethod
    def get_by_id(id_departamento: int) -> Optional[DepartamentoUNAM]:
        """
        Obtiene un departamento por su ID.

        Args:
            id_departamento: ID del departamento

        Returns:
            Optional[DepartamentoUNAM]: El departamento encontrado o None
        """
        try:
            if not id_departamento or not isinstance(id_departamento, int):
                raise ValueError("ID de departamento inválido")

            departamento = DepartamentoUNAM.query.get(id_departamento)
            if not departamento:
                logger.warning(f"Departamento no encontrado con ID: {id_departamento}")
            return departamento
        except SQLAlchemyError as e:
            logger.error(
                f"Error al obtener departamento por ID {id_departamento}: {str(e)}"
            )
            raise RuntimeError("Error al consultar el departamento") from e

    @staticmethod
    def get_by_nombre(nombre: str) -> Optional[DepartamentoUNAM]:
        """
        Obtiene un departamento por su nombre.

        Args:
            nombre: Nombre del departamento

        Returns:
            Optional[DepartamentoUNAM]: El departamento encontrado o None
        """
        try:
            if not nombre or not isinstance(nombre, str):
                raise ValueError("Nombre de departamento inválido")

            return DepartamentoUNAM.query.filter_by(nombre=nombre).first()
        except SQLAlchemyError as e:
            logger.error(
                f"Error al obtener departamento por nombre '{nombre}': {str(e)}"
            )
            raise RuntimeError("Error al consultar el departamento") from e

    @staticmethod
    def _exists_departamento(nombre: str, exclude_id: Optional[int] = None) -> bool:
        """
        Verifica si ya existe un departamento con el mismo nombre.

        Args:
            nombre: Nombre a verificar
            exclude_id: ID a excluir de la verificación (para actualizaciones)

        Returns:
            bool: True si existe, False en caso contrario
        """
        query: Query = DepartamentoUNAM.query.filter_by(nombre=nombre)
        if exclude_id is not None:
            query = query.filter(DepartamentoUNAM.id_departamento != exclude_id)
        return query.first() is not None

    @staticmethod
    def create(
        nombre: str, prefijo: str, puntos_entrega: Optional[List[Any]] = None
    ) -> DepartamentoUNAM:
        """
        Crea un nuevo departamento.

        Args:
            nombre: Nombre del departamento (único)
            prefijo: Prefijo del departamento
            puntos_entrega: Lista de puntos de entrega (opcional)

        Returns:
            DepartamentoUNAM: El departamento creado

        Raises:
            ValueError: Si los datos son inválidos o el nombre ya existe
            RuntimeError: Si hay error en la base de datos
        """
        try:
            # Validaciones
            if not nombre or not isinstance(nombre, str):
                raise ValueError("El nombre es requerido y debe ser texto")

            if not prefijo or not isinstance(prefijo, str):
                raise ValueError("El prefijo es requerido y debe ser texto")

            if len(nombre.strip()) == 0 or len(prefijo.strip()) == 0:
                raise ValueError("El nombre y prefijo no pueden estar vacíos")

            # Verificar nombre único
            if DepartamentoUNAMService._exists_departamento(nombre):
                raise ValueError(f"Ya existe un departamento con el nombre '{nombre}'")

            # Crear departamento
            departamento = DepartamentoUNAM(
                nombre=nombre.strip(),
                prefijo=prefijo.strip().upper(),
                puntos_entrega=list(puntos_entrega) if puntos_entrega else [],
            )

            db.session.add(departamento)
            db.session.commit()

            logger.info(
                f"Departamento creado exitosamente: ID={departamento.id_departamento}, Nombre='{nombre}'"
            )
            return departamento

        except IntegrityError as e:
            db.session.rollback()
            logger.error(
                f"Error de integridad al crear departamento '{nombre}': {str(e)}"
            )
            raise ValueError(
                "Error de integridad en la base de datos (posible duplicado)"
            ) from e
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(
                f"Error en base de datos al crear departamento '{nombre}': {str(e)}"
            )
            raise RuntimeError(
                "Error al guardar el departamento en la base de datos"
            ) from e
        except ValueError as e:
            db.session.rollback()
            logger.warning(f"Validación fallida al crear departamento: {str(e)}")
            raise
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error inesperado al crear departamento '{nombre}': {str(e)}")
            raise RuntimeError("Error inesperado al crear el departamento") from e

    @staticmethod
    def update(
        id_departamento: int,
        nombre: Optional[str] = None,
        prefijo: Optional[str] = None,
        puntos_entrega: Optional[List[Any]] = None,
    ) -> DepartamentoUNAM:
        """
        Actualiza un departamento existente.

        Args:
            id_departamento: ID del departamento a actualizar
            nombre: Nuevo nombre (opcional)
            prefijo: Nuevo prefijo (opcional)
            puntos_entrega: Nueva lista de puntos de entrega (opcional)

        Returns:
            DepartamentoUNAM: El departamento actualizado

        Raises:
            ValueError: Si los datos son inválidos o el nombre ya existe
            RuntimeError: Si hay error en la base de datos
        """
        try:
            # Validar ID
            if not id_departamento or not isinstance(id_departamento, int):
                raise ValueError("ID de departamento inválido")

            # Obtener departamento
            departamento: Optional[DepartamentoUNAM] = DepartamentoUNAM.query.get(
                id_departamento
            )
            if not departamento:
                raise ValueError(f"No existe departamento con ID {id_departamento}")

            # Validar y actualizar nombre
            if nombre is not None:
                if not isinstance(nombre, str) or len(nombre.strip()) == 0:
                    raise ValueError("El nombre no puede estar vacío")

                nombre_limpio: str = nombre.strip()
                if nombre_limpio != departamento.nombre:
                    if DepartamentoUNAMService._exists_departamento(
                        nombre_limpio, id_departamento
                    ):
                        raise ValueError(
                            f"Ya existe otro departamento con el nombre '{nombre_limpio}'"
                        )
                    departamento.nombre = nombre_limpio

            # Validar y actualizar prefijo
            if prefijo is not None:
                if not isinstance(prefijo, str) or len(prefijo.strip()) == 0:
                    raise ValueError("El prefijo no puede estar vacío")
                departamento.prefijo = prefijo.strip().upper()

            # Actualizar puntos de entrega
            if puntos_entrega is not None:
                departamento.puntos_entrega = (
                    list(puntos_entrega) if puntos_entrega else []
                )

            # Guardar cambios
            db.session.commit()

            logger.info(f"Departamento actualizado exitosamente: ID={id_departamento}")
            return departamento

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(
                f"Error en base de datos al actualizar departamento {id_departamento}: {str(e)}"
            )
            raise RuntimeError(
                "Error al actualizar el departamento en la base de datos"
            ) from e
        except ValueError as e:
            db.session.rollback()
            logger.warning(
                f"Validación fallida al actualizar departamento {id_departamento}: {str(e)}"
            )
            raise
        except Exception as e:
            db.session.rollback()
            logger.error(
                f"Error inesperado al actualizar departamento {id_departamento}: {str(e)}"
            )
            raise RuntimeError("Error inesperado al actualizar el departamento") from e

    @staticmethod
    def delete(id_departamento: int) -> bool:
        """
        Elimina un departamento.

        Args:
            id_departamento: ID del departamento a eliminar

        Returns:
            bool: True si se eliminó correctamente

        Raises:
            ValueError: Si el ID es inválido o el departamento no existe
            RuntimeError: Si hay error en la base de datos
        """
        try:
            # Validar ID
            if not id_departamento or not isinstance(id_departamento, int):
                raise ValueError("ID de departamento inválido")

            # Obtener departamento
            departamento: Optional[DepartamentoUNAM] = DepartamentoUNAM.query.get(
                id_departamento
            )
            if not departamento:
                raise ValueError(f"No existe departamento con ID {id_departamento}")

            # Eliminar
            db.session.delete(departamento)
            db.session.commit()

            logger.info(
                f"Departamento eliminado exitosamente: ID={id_departamento}, Nombre='{departamento.nombre}'"
            )
            return True

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(
                f"Error en base de datos al eliminar departamento {id_departamento}: {str(e)}"
            )
            raise RuntimeError(
                "Error al eliminar el departamento de la base de datos"
            ) from e
        except ValueError as e:
            db.session.rollback()
            logger.warning(
                f"Validación fallida al eliminar departamento {id_departamento}: {str(e)}"
            )
            raise
        except Exception as e:
            db.session.rollback()
            logger.error(
                f"Error inesperado al eliminar departamento {id_departamento}: {str(e)}"
            )
            raise RuntimeError("Error inesperado al eliminar el departamento") from e
