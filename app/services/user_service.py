import re
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.models import Usuario

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,45}$")
MIN_PASSWORD_LENGTH = 8


def _validate_email(email: str) -> Optional[str]:
    if not email:
        return "El email es requerido"
    if not EMAIL_RE.match(email):
        return "El email no tiene un formato válido"
    return None


def _validate_username(username: str) -> Optional[str]:
    if not username:
        return "El nombre de usuario es requerido"
    if not USERNAME_RE.match(username):
        return (
            "El nombre de usuario debe tener entre 3 y 45 caracteres y solo puede "
            "contener letras, números, guiones, puntos o guiones bajos"
        )
    return None


def _validate_password(password: str) -> Optional[str]:
    if not password:
        return "La contraseña es requerida"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres"
    if not re.search(r"[A-Z]", password):
        return "La contraseña debe contener al menos una letra mayúscula"
    if not re.search(r"[0-9]", password):
        return "La contraseña debe contener al menos un número"
    return None


def _validate_role(role: str) -> Optional[str]:
    if role not in ("admin", "vendedor"):
        return "El rol debe ser 'admin' o 'vendedor'"
    return None


def _validate_nombre(value: str) -> Optional[str]:
    """Valida el campo nombre — String(100)."""
    if not value:
        return "El nombre es requerido"
    if len(value) > 100:
        return "El nombre no puede exceder 100 caracteres"
    return None


def _validate_apellido(value: str, field_label: str, required: bool = True) -> Optional[str]:
    """Valida ap_paterno y ap_materno — String(45)."""
    if not value:
        return f"{field_label} es requerido" if required else None
    if len(value) > 45:
        return f"{field_label} no puede exceder 45 caracteres"
    return None


class UserService:

    @staticmethod
    def get_all_users() -> List[Usuario]:
        """Devuelve todos los usuarios activos (sin soft-delete)."""
        try:
            return (
                Usuario.query
                .filter(Usuario.deleted_at.is_(None))
                .order_by(Usuario.id_usuario)
                .all()
            )
        except SQLAlchemyError as e:
            print(f"Error al obtener usuarios: {e}")
            return []

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[Usuario]:
        """Devuelve un usuario activo por su ID."""
        try:
            return (
                Usuario.query
                .filter(
                    Usuario.id_usuario == user_id,
                    Usuario.deleted_at.is_(None),
                )
                .first()
            )
        except SQLAlchemyError as e:
            print(f"Error al obtener usuario {user_id}: {e}")
            return None

    @staticmethod
    def get_usuarios_by_role(role: str) -> List[Usuario]:
        """Devuelve todos los usuarios activos con un rol específico."""
        error = _validate_role(role)
        if error:
            print(f"Rol inválido en get_usuarios_by_role: {error}")
            return []
        try:
            return (
                Usuario.query
                .filter(
                    Usuario.role == role,
                    Usuario.deleted_at.is_(None),
                )
                .order_by(Usuario.username)
                .all()
            )
        except SQLAlchemyError as e:
            print(f"Error al obtener usuarios con rol {role}: {e}")
            return []

    @staticmethod
    def get_user_by_username(username: str) -> Optional[Usuario]:
        """Devuelve un usuario activo por su username (case-insensitive)."""
        username = (username or "").strip()
        error = _validate_username(username)
        if error:
            print(f"Username inválido en get_user_by_username: {error}")
            return None
        try:
            return (
                Usuario.query
                .filter(
                    Usuario.username.ilike(username),
                    Usuario.deleted_at.is_(None),
                )
                .first()
            )
        except SQLAlchemyError as e:
            print(f"Error al obtener usuario por username '{username}': {e}")
            return None

    @staticmethod
    def create_user(
        username: str,
        email: str,
        role: str,
        nombre: str,
        ap_paterno: str,
        password: str,
        ap_materno: Optional[str] = None,
    ) -> Tuple[Optional[Usuario], Optional[str]]:
        """Crea un nuevo usuario tras validar todas las entradas."""
        # Sanitize
        username = (username or "").strip()
        email = (email or "").strip().lower()
        role = (role or "").strip()
        nombre = (nombre or "").strip()
        ap_paterno = (ap_paterno or "").strip()
        ap_materno = (ap_materno or "").strip() or None

        # Validate
        for error in (
            _validate_username(username),
            _validate_email(email),
            _validate_role(role),
            _validate_nombre(nombre),
            _validate_apellido(ap_paterno, "El apellido paterno", required=True),
            _validate_apellido(ap_materno, "El apellido materno", required=False),
            _validate_password(password),
        ):
            if error:
                return None, error

        try:
            if Usuario.query.filter_by(username=username).first():
                return None, "El nombre de usuario ya está en uso"
            if Usuario.query.filter_by(email=email).first():
                return None, "El email ya está registrado"

            user = Usuario(
                username=username,
                email=email,
                role=role,
                nombre=nombre,
                ap_paterno=ap_paterno,
                ap_materno=ap_materno,
                deleted_at=None,
            )
            user.set_password(password)

            db.session.add(user)
            db.session.commit()
            return user, None

        except SQLAlchemyError as e:
            db.session.rollback()
            error_msg = f"Error al crear el usuario: {e}"
            print(error_msg)
            return None, error_msg

    @staticmethod
    def update_user(
        user_id: int,
        username: str,
        email: str,
        role: str,
        nombre: str,
        ap_paterno: str,
        password: Optional[str] = None,
        ap_materno: Optional[str] = None,
    ) -> Tuple[Optional[Usuario], Optional[str]]:
        """Actualiza un usuario existente tras validar todas las entradas."""
        # Sanitize
        username = (username or "").strip()
        email = (email or "").strip().lower()
        role = (role or "").strip()
        nombre = (nombre or "").strip()
        ap_paterno = (ap_paterno or "").strip()
        ap_materno = (ap_materno or "").strip() or None

        # Validate campos obligatorios
        for error in (
            _validate_username(username),
            _validate_email(email),
            _validate_role(role),
            _validate_nombre(nombre),
            _validate_apellido(ap_paterno, "El apellido paterno", required=True),
            _validate_apellido(ap_materno, "El apellido materno", required=False),
        ):
            if error:
                return None, error

        # Validar contraseña solo si se quiere cambiar
        if password:
            error = _validate_password(password)
            if error:
                return None, error

        try:
            user = (
                Usuario.query
                .filter(
                    Usuario.id_usuario == user_id,
                    Usuario.deleted_at.is_(None),
                )
                .first()
            )
            if not user:
                return None, "Usuario no encontrado"

            # Verificar duplicados excluyendo al propio usuario
            duplicate_username = (
                Usuario.query
                .filter(Usuario.username == username, Usuario.id_usuario != user_id)
                .first()
            )
            if duplicate_username:
                return None, "El nombre de usuario ya está en uso"

            duplicate_email = (
                Usuario.query
                .filter(Usuario.email == email, Usuario.id_usuario != user_id)
                .first()
            )
            if duplicate_email:
                return None, "El email ya está registrado"

            user.username = username
            user.email = email
            user.role = role
            user.nombre = nombre
            user.ap_paterno = ap_paterno
            user.ap_materno = ap_materno

            if password:
                user.set_password(password)

            db.session.commit()
            return user, None

        except SQLAlchemyError as e:
            db.session.rollback()
            error_msg = f"Error al actualizar el usuario: {e}"
            print(error_msg)
            return None, error_msg

    @staticmethod
    def delete_user(user_id: int) -> Tuple[bool, Optional[str]]:
        """Soft-delete de un usuario."""
        try:
            user = (
                Usuario.query
                .filter(
                    Usuario.id_usuario == user_id,
                    Usuario.deleted_at.is_(None),
                )
                .first()
            )
            if not user:
                return False, "Usuario no encontrado"

            user.deleted_at = datetime.now()
            db.session.commit()
            return True, None

        except SQLAlchemyError as e:
            db.session.rollback()
            error_msg = f"Error al eliminar el usuario: {e}"
            print(error_msg)
            return False, error_msg