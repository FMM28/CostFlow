from datetime import datetime

from app.models import Usuario
from app.extensions import db
from typing import List, Optional, Tuple
from sqlalchemy.exc import SQLAlchemyError


class UserService:
    
    @staticmethod
    def get_all_users() -> List[Usuario]:
        """Obtiene todos los usuarios"""
        try:
            return Usuario.query.order_by(Usuario.id_usuario).all()
        except SQLAlchemyError as e:
            print(f"Error al obtener usuarios: {e}")
            return []
    
    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[Usuario]:
        """Obtiene un usuario por su ID"""
        try:
            return Usuario.query.get(user_id)
        except SQLAlchemyError as e:
            print(f"Error al obtener usuario {user_id}: {e}")
            return None
    
    @staticmethod
    def get_usuarios_by_role(role: str) -> List[Usuario]:
        """Obtiene todos los usuarios con un rol específico"""
        try:
            return Usuario.query.filter_by(role=role).order_by(Usuario.username).all()
        except SQLAlchemyError as e:
            print(f"Error al obtener usuarios con rol {role}: {e}")
            return []
    
    @staticmethod
    def create_user(username: str, email: str, role: str, nombre: str, ap_paterno: str, password: str, ap_materno: Optional[str] = None) -> Tuple[Optional[Usuario], Optional[str]]:
        """Crea un nuevo usuario"""
        try:
            username = username.strip()
            email = email.strip()
            role = role.strip()
            nombre = nombre.strip()
            ap_paterno = ap_paterno.strip()
            ap_materno = ap_materno.strip() if ap_materno else None

            if not username:
                return None, "El nombre de usuario es requerido"
            
            if not nombre:
                return None, "El nombre es requerido"
            
            if not ap_paterno:
                return None, "El apellido paterno es requerido"
            
            if not password:
                return None, "La contraseña es requerida"
            
            if not email:
                return None, "El email es requerido"
            
            if role not in ["admin", "vendedor"]:
                return None, "El rol debe ser 'admin' o 'vendedor'"
            
            user = Usuario(
                username=username,
                email=email,
                role=role,
                nombre=nombre,
                ap_paterno=ap_paterno,
                ap_materno=ap_materno,
                deleted_at=None
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            return user, None
        except SQLAlchemyError as e:
            db.session.rollback()
            error_msg = f"Error al crear el usuario: {str(e)}"
            print(error_msg)
            return None, error_msg

    @staticmethod
    def update_user(user_id: int, username: str, email: str, role: str, nombre: str, ap_paterno: str, password: Optional[str] = None, ap_materno: Optional[str] = None) -> Tuple[Optional[Usuario], Optional[str]]:
        """Actualiza un usuario existente"""
        try:
            user = Usuario.query.get(user_id)
            if not user:
                return None, "Usuario no encontrado"
            
            username = username.strip()
            email = email.strip()
            role = role.strip()
            nombre = nombre.strip()
            ap_paterno = ap_paterno.strip()
            ap_materno = ap_materno.strip() if ap_materno else None
            
            if not username:
                return None, "El nombre de usuario es requerido"
            
            if not nombre:
                return None, "El nombre es requerido"
            
            if not ap_paterno:
                return None, "El apellido paterno es requerido"
            
            if not email:
                return None, "El email es requerido"
            
            if role not in ["admin", "vendedor"]:
                return None, "El rol debe ser 'admin' o 'vendedor'"
            
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
            error_msg = f"Error al actualizar el usuario: {str(e)}"
            print(error_msg)
            return None, error_msg
    
    @staticmethod
    def delete_user(user_id: int) -> Tuple[bool, Optional[str]]:
        """Elimina un usuario"""
        try:
            user = Usuario.query.get(user_id)
            if not user:
                return False, "Usuario no encontrado"
            
            user.deleted_at = datetime.now()
            db.session.commit()
            return True, None
        except SQLAlchemyError as e:
            db.session.rollback()
            error_msg = f"Error al eliminar el usuario: {str(e)}"
            print(error_msg)
            return False, error_msg