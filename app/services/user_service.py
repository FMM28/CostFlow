from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Union
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from app.extensions import db
from app.models import Usuario

logger = logging.getLogger(__name__)

# Regex patterns and constants
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,45}$")
MIN_PASSWORD_LENGTH = 8
VALID_ROLES = ("admin", "vendedor")


def _validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """Valida el formato del email. Retorna (is_valid, error_message)."""
    if not email or not email.strip():
        return False, "El email es requerido."
    email = email.strip()
    if not EMAIL_RE.match(email):
        return False, "El email no tiene un formato válido."
    return True, None


def _validate_username(username: str) -> Tuple[bool, Optional[str]]:
    """Valida el formato del username. Retorna (is_valid, error_message)."""
    if not username or not username.strip():
        return False, "El nombre de usuario es requerido."
    username = username.strip()
    if not USERNAME_RE.match(username):
        return False, (
            "El nombre de usuario debe tener entre 3 y 45 caracteres y solo puede "
            "contener letras, números, guiones, puntos o guiones bajos."
        )
    return True, None


def _validate_password(password: str) -> Tuple[bool, Optional[str]]:
    """Valida la fortaleza de la contraseña. Retorna (is_valid, error_message)."""
    if not password:
        return False, "La contraseña es requerida."
    if len(password) < MIN_PASSWORD_LENGTH:
        return (
            False,
            f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.",
        )
    if not re.search(r"[A-Z]", password):
        return False, "La contraseña debe contener al menos una letra mayúscula."
    if not re.search(r"[0-9]", password):
        return False, "La contraseña debe contener al menos un número."
    return True, None


def _validate_role(role: str) -> Tuple[bool, Optional[str]]:
    """Valida que el rol sea permitido. Retorna (is_valid, error_message)."""
    if not role or role.strip() not in VALID_ROLES:
        return False, f"El rol debe ser uno de: {', '.join(VALID_ROLES)}."
    return True, None


def _validate_nombre(value: str) -> Tuple[bool, Optional[str]]:
    """Valida el campo nombre — String(100). Retorna (is_valid, error_message)."""
    if not value or not value.strip():
        return False, "El nombre es requerido."
    if len(value.strip()) > 100:
        return False, "El nombre no puede exceder 100 caracteres."
    return True, None


def _validate_apellido(
    value: Optional[str], field_label: str, required: bool = True
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Valida ap_paterno y ap_materno — String(45).
    Retorna (is_valid, error_message, normalized_value).
    """
    if not value or not value.strip():
        if required:
            return False, f"{field_label} es requerido.", None
        return True, None, None
    value = value.strip()
    if len(value) > 45:
        return False, f"{field_label} no puede exceder 45 caracteres.", None
    return True, None, value


class UserService:
    """Servicio para gestión de usuarios con manejo de errores sin excepciones."""

    @staticmethod
    def get_all(include_deleted: bool = False) -> List[Usuario]:
        """
        Retorna todos los usuarios ordenados por username.

        Args:
            include_deleted: Si es True incluye registros con soft delete.

        Returns:
            List[Usuario]: Lista de usuarios (vacía si hay error).
        """
        try:
            query = Usuario.query
            if not include_deleted:
                query = query.filter(Usuario.deleted_at.is_(None))
            return query.order_by(Usuario.username).all()
        except SQLAlchemyError as exc:
            logger.exception("Error al obtener usuarios: %s", exc)
            return []

    @staticmethod
    def get_by_id(id_usuario: int, include_deleted: bool = False) -> Optional[Usuario]:
        """
        Retorna un usuario por su PK.

        Returns:
            Optional[Usuario]: Usuario encontrado o None si no existe/hay error.
        """
        try:
            usuario: Optional[Usuario] = db.session.get(Usuario, id_usuario)
        except SQLAlchemyError as exc:
            logger.exception("Error al buscar usuario id=%s: %s", id_usuario, exc)
            return None

        if usuario is None:
            logger.warning("Usuario con id %s no encontrado.", id_usuario)
            return None

        if not include_deleted and usuario.deleted_at is not None:
            logger.warning("Usuario con id %s ha sido eliminado.", id_usuario)
            return None

        return usuario

    @staticmethod
    def get_by_username(
        username: str, include_deleted: bool = False
    ) -> Optional[Usuario]:
        """
        Busca un usuario por username (case-insensitive).

        Returns:
            Optional[Usuario]: Usuario encontrado o None si no existe/error de validación.
        """
        is_valid, error = _validate_username(username)
        if not is_valid:
            logger.warning("Username inválido '%s': %s", username, error)
            return None

        username = username.strip()
        try:
            query = Usuario.query.filter(Usuario.username.ilike(username))
            if not include_deleted:
                query = query.filter(Usuario.deleted_at.is_(None))
            return query.first()
        except SQLAlchemyError as exc:
            logger.exception(
                "Error al buscar usuario por username='%s': %s", username, exc
            )
            return None

    @staticmethod
    def search_by_nombre(nombre: str, include_deleted: bool = False) -> List[Usuario]:
        """
        Busca usuarios cuyo nombre o apellidos contengan la cadena indicada.

        Returns:
            List[Usuario]: Lista de usuarios encontrados (vacía si no hay resultados o error).
        """
        if not nombre or not nombre.strip():
            logger.warning("Término de búsqueda vacío.")
            return []

        try:
            search_term = f"%{nombre.strip()}%"
            query = Usuario.query.filter(
                (Usuario.nombre.ilike(search_term))
                | (Usuario.ap_paterno.ilike(search_term))
                | (Usuario.ap_materno.ilike(search_term))
            )
            if not include_deleted:
                query = query.filter(Usuario.deleted_at.is_(None))
            return query.order_by(Usuario.nombre).all()
        except SQLAlchemyError as exc:
            logger.exception(
                "Error al buscar usuarios por nombre='%s': %s", nombre, exc
            )
            return []

    @staticmethod
    def get_by_role(role: str, include_deleted: bool = False) -> List[Usuario]:
        """
        Retorna todos los usuarios con un rol específico.

        Returns:
            List[Usuario]: Lista de usuarios (vacía si rol inválido o error).
        """
        is_valid, error = _validate_role(role)
        if not is_valid:
            logger.warning("Rol inválido '%s': %s", role, error)
            return []

        try:
            query = Usuario.query.filter(Usuario.role == role.strip())
            if not include_deleted:
                query = query.filter(Usuario.deleted_at.is_(None))
            return query.order_by(Usuario.username).all()
        except SQLAlchemyError as exc:
            logger.exception("Error al obtener usuarios con rol='%s': %s", role, exc)
            return []

    @staticmethod
    def create(
        username: str,
        email: str,
        role: str,
        nombre: str,
        ap_paterno: str,
        password: str,
        ap_materno: Optional[str] = None,
    ) -> Tuple[Optional[Usuario], Optional[str]]:
        """
        Crea un nuevo usuario tras validar todas las entradas.

        Returns:
            Tuple[Optional[Usuario], Optional[str]]: (usuario_creado, mensaje_error)
        """
        # Validaciones
        is_valid, error = _validate_username(username)
        if not is_valid:
            return None, error

        is_valid, error = _validate_email(email)
        if not is_valid:
            return None, error

        is_valid, error = _validate_role(role)
        if not is_valid:
            return None, error

        is_valid, error = _validate_nombre(nombre)
        if not is_valid:
            return None, error

        is_valid, error, ap_paterno_norm = _validate_apellido(
            ap_paterno, "El apellido paterno", required=True
        )
        if not is_valid:
            return None, error

        is_valid, error, ap_materno_norm = _validate_apellido(
            ap_materno, "El apellido materno", required=False
        )
        if not is_valid:
            return None, error

        is_valid, error = _validate_password(password)
        if not is_valid:
            return None, error

        # Sanitize inputs
        username = username.strip()
        email = email.strip().lower()
        role = role.strip()
        nombre = nombre.strip()

        # Verificar unicidad
        try:
            if Usuario.query.filter(Usuario.username.ilike(username)).first():
                return None, "El nombre de usuario ya está en uso."
            if Usuario.query.filter(Usuario.email.ilike(email)).first():
                return None, "El email ya está registrado."
        except SQLAlchemyError as exc:
            logger.exception("Error al verificar unicidad: %s", exc)
            return None, "Error de base de datos al verificar datos existentes."

        usuario = Usuario(
            username=username,
            email=email,
            role=role,
            nombre=nombre,
            ap_paterno=ap_paterno_norm,
            ap_materno=ap_materno_norm,
            deleted_at=None,
        )
        usuario.set_password(password)

        try:
            db.session.add(usuario)
            db.session.commit()
            logger.info(
                "Usuario creado: id=%s username='%s'.", usuario.id_usuario, username
            )
            return usuario, None
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning(
                "IntegrityError al crear usuario username='%s': %s", username, exc
            )
            return None, "Conflicto de datos al crear el usuario."
        except OperationalError as exc:
            db.session.rollback()
            logger.exception("OperationalError al crear usuario: %s", exc)
            return None, "Error de conexión con la base de datos."
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.exception("Error inesperado al crear usuario: %s", exc)
            return None, "Error inesperado al crear el usuario."

    @staticmethod
    def update(
        id_usuario: int,
        username: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None,
        nombre: Optional[str] = None,
        ap_paterno: Optional[str] = None,
        password: Optional[str] = None,
        ap_materno: Optional[str] = None,
    ) -> Tuple[Optional[Usuario], Optional[str]]:
        """
        Actualiza los campos proporcionados de un usuario activo.

        Returns:
            Tuple[Optional[Usuario], Optional[str]]: (usuario_actualizado, mensaje_error)
        """
        usuario = UserService.get_by_id(id_usuario)
        if usuario is None:
            return None, f"Usuario con id {id_usuario} no encontrado o eliminado."

        # Validar y actualizar campos proporcionados
        if username is not None:
            is_valid, error = _validate_username(username)
            if not is_valid:
                return None, error

            username = username.strip()
            try:
                duplicate = Usuario.query.filter(
                    Usuario.username.ilike(username), Usuario.id_usuario != id_usuario
                ).first()
                if duplicate:
                    return None, "El nombre de usuario ya está en uso."
            except SQLAlchemyError as exc:
                logger.exception("Error al verificar unicidad de username: %s", exc)
                return None, "Error de base de datos al verificar username."

            usuario.username = username

        if email is not None:
            is_valid, error = _validate_email(email)
            if not is_valid:
                return None, error

            email = email.strip().lower()
            try:
                duplicate = Usuario.query.filter(
                    Usuario.email.ilike(email), Usuario.id_usuario != id_usuario
                ).first()
                if duplicate:
                    return None, "El email ya está registrado."
            except SQLAlchemyError as exc:
                logger.exception("Error al verificar unicidad de email: %s", exc)
                return None, "Error de base de datos al verificar email."

            usuario.email = email

        if role is not None:
            is_valid, error = _validate_role(role)
            if not is_valid:
                return None, error

            usuario.role = role.strip()

        if nombre is not None:
            is_valid, error = _validate_nombre(nombre)
            if not is_valid:
                return None, error

            usuario.nombre = nombre.strip()

        if ap_paterno is not None:
            is_valid, error, ap_paterno_norm = _validate_apellido(
                ap_paterno, "El apellido paterno", required=True
            )
            if not is_valid:
                return None, error

            usuario.ap_paterno = ap_paterno_norm

        if ap_materno is not None:
            is_valid, error, ap_materno_norm = _validate_apellido(
                ap_materno, "El apellido materno", required=False
            )
            if not is_valid:
                return None, error

            usuario.ap_materno = ap_materno_norm

        if password is not None:
            is_valid, error = _validate_password(password)
            if not is_valid:
                return None, error

            usuario.set_password(password)

        try:
            db.session.commit()
            logger.info("Usuario actualizado: id=%s.", id_usuario)
            return usuario, None
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning(
                "IntegrityError al actualizar usuario id=%s: %s", id_usuario, exc
            )
            return None, "Conflicto de datos al actualizar el usuario."
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.exception("Error al actualizar usuario id=%s: %s", id_usuario, exc)
            return None, "Error de base de datos al actualizar el usuario."

    @staticmethod
    def soft_delete(id_usuario: int) -> Tuple[bool, Optional[str]]:
        """
        Marca el usuario como eliminado sin borrarlo de la base de datos.

        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        usuario = UserService.get_by_id(id_usuario)
        if usuario is None:
            return False, f"Usuario con id {id_usuario} no encontrado o ya eliminado."

        try:
            usuario.deleted_at = datetime.now(tz=timezone.utc)
            db.session.commit()
            logger.info("Usuario eliminado (soft): id=%s.", id_usuario)
            return True, None
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.exception(
                "Error al hacer soft delete de usuario id=%s: %s", id_usuario, exc
            )
            return False, "Error de base de datos al eliminar el usuario."

    @staticmethod
    def restore(id_usuario: int) -> Tuple[bool, Optional[str]]:
        """
        Restaura un usuario que fue eliminado con soft delete.

        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        usuario = UserService.get_by_id(id_usuario, include_deleted=True)
        if usuario is None:
            return False, f"Usuario con id {id_usuario} no encontrado."

        if usuario.deleted_at is None:
            return False, f"El usuario con id {id_usuario} no está eliminado."

        try:
            usuario.deleted_at = None
            db.session.commit()
            logger.info("Usuario restaurado: id=%s.", id_usuario)
            return True, None
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.exception("Error al restaurar usuario id=%s: %s", id_usuario, exc)
            return False, "Error de base de datos al restaurar el usuario."

    @staticmethod
    def hard_delete(id_usuario: int) -> Tuple[bool, Optional[str]]:
        """
        Elimina permanentemente el usuario de la base de datos.

        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        usuario = UserService.get_by_id(id_usuario, include_deleted=True)
        if usuario is None:
            return False, f"Usuario con id {id_usuario} no encontrado."

        try:
            db.session.delete(usuario)
            db.session.commit()
            logger.info("Usuario eliminado permanentemente: id=%s.", id_usuario)
            return True, None
        except IntegrityError as exc:
            db.session.rollback()
            logger.warning(
                "IntegrityError al eliminar usuario id=%s (tiene relaciones asociadas): %s",
                id_usuario,
                exc,
            )
            return (
                False,
                "No se puede eliminar permanentemente el usuario porque tiene registros asociados.",
            )
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.exception("Error al eliminar usuario id=%s: %s", id_usuario, exc)
            return False, "Error de base de datos al eliminar el usuario."

    @staticmethod
    def change_password(
        id_usuario: int, current_password: str, new_password: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Cambia la contraseña de un usuario activo tras validar la actual.

        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        usuario = UserService.get_by_id(id_usuario)
        if usuario is None:
            return False, f"Usuario con id {id_usuario} no encontrado o eliminado."

        is_valid, error = _validate_password(new_password)
        if not is_valid:
            return False, error

        if not usuario.check_password(current_password):
            return False, "La contraseña actual es incorrecta."

        try:
            usuario.set_password(new_password)
            db.session.commit()
            logger.info("Contraseña cambiada para usuario: id=%s.", id_usuario)
            return True, None
        except SQLAlchemyError as exc:
            db.session.rollback()
            logger.exception(
                "Error al cambiar contraseña de usuario id=%s: %s", id_usuario, exc
            )
            return False, "Error de base de datos al cambiar la contraseña."
