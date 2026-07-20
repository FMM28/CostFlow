from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import SesionProveedor
from app.cache.redis_cache import RedisCache
from app.cache.redis_keys import RedisKeys

logger = logging.getLogger(__name__)


class SesionProveedorService:
    _fernet = None

    @classmethod
    def _cache(cls):
        return RedisCache()

    @classmethod
    def _get_fernet(cls) -> Fernet:
        if cls._fernet is None:
            try:
                encryption_key = current_app.config.get("SESSION_ENCRYPTION_KEY")
                if not encryption_key:
                    raise ValueError("SESSION_ENCRYPTION_KEY not configured")
                cls._fernet = Fernet(encryption_key.encode())
            except Exception as e:
                logger.error(f"Failed to initialize Fernet: {e}")
                raise RuntimeError("Encryption service unavailable") from e
        return cls._fernet

    @classmethod
    def obtener(cls, proveedor: str) -> dict | list | None:
        """
        Obtiene la sesión de un proveedor.
        """
        if not proveedor or not proveedor.strip():
            logger.warning("Empty proveedor provided to obtener")
            return None

        proveedor = proveedor.upper().strip()
        key = RedisKeys.session(proveedor)

        try:
            cookies = cls._cache().get_json(key)
            if cookies is not None:
                logger.debug(f"Session retrieved from cache for {proveedor}")
                return cookies
        except Exception as e:
            logger.error(f"Cache error while retrieving session for {proveedor}: {e}")

        try:
            sesion = SesionProveedor.query.get(proveedor)
            if sesion is None:
                logger.info(f"No session found for {proveedor}")
                return None

            if not sesion.cookies:
                logger.warning(f"Empty cookies field for {proveedor}")
                return None

            cookies = cls._descifrar(sesion.cookies)

            try:
                cls._cache().set_json(key, cookies)
                logger.debug(f"Session cached for {proveedor}")
            except Exception as e:
                logger.error(f"Failed to cache session for {proveedor}: {e}")

            return cookies

        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving session for {proveedor}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving session for {proveedor}: {e}")
            return None

    @classmethod
    def guardar(cls, proveedor: str, cookies: dict | list) -> bool:
        """
        Guarda la sesión en Redis y una copia cifrada en la base de datos.
        """
        if not proveedor or not proveedor.strip():
            logger.error("Cannot save session: empty proveedor")
            return False

        if not cookies:
            logger.warning(f"Empty cookies provided for {proveedor}")
            return False

        proveedor = proveedor.upper().strip()
        success = True

        try:
            cls._cache().set_json(
                RedisKeys.session(proveedor),
                cookies,
            )
            logger.debug(f"Session cached for {proveedor}")
        except Exception as e:
            logger.error(f"Failed to cache session for {proveedor}: {e}")
            success = False

        try:
            encrypted_cookies = cls._cifrar(cookies)
            now = datetime.now(timezone.utc)

            sesion = SesionProveedor.query.get(proveedor)
            if sesion is None:
                sesion = SesionProveedor(
                    proveedor=proveedor,
                    cookies=encrypted_cookies,
                    updated_at=now,
                )
                db.session.add(sesion)
                logger.info(f"Created new session record for {proveedor}")
            else:
                sesion.cookies = encrypted_cookies
                sesion.updated_at = now
                logger.debug(f"Updated session record for {proveedor}")

            db.session.commit()
            logger.debug(f"Session saved to database for {proveedor}")

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error saving session for {proveedor}: {e}")
            return False
        except Exception as e:
            db.session.rollback()
            logger.error(f"Unexpected error saving session for {proveedor}: {e}")
            return False

        return success

    @classmethod
    def eliminar(cls, proveedor: str) -> bool:
        """
        Elimina la sesión del proveedor.
        """
        if not proveedor or not proveedor.strip():
            logger.error("Cannot delete session: empty proveedor")
            return False

        proveedor = proveedor.upper().strip()
        success = True

        try:
            cls._cache().delete(RedisKeys.session(proveedor))
            logger.debug(f"Session deleted from cache for {proveedor}")
        except Exception as e:
            logger.error(f"Failed to delete session from cache for {proveedor}: {e}")
            success = False

        try:
            sesion = SesionProveedor.query.get(proveedor)
            if sesion is not None:
                db.session.delete(sesion)
                db.session.commit()
                logger.info(f"Session deleted from database for {proveedor}")
            else:
                logger.debug(f"No session record found to delete for {proveedor}")

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error deleting session for {proveedor}: {e}")
            return False
        except Exception as e:
            db.session.rollback()
            logger.error(f"Unexpected error deleting session for {proveedor}: {e}")
            return False

        return success

    @classmethod
    def _cifrar(cls, cookies: dict | list) -> str:
        """
        Cifra las cookies para almacenamiento en base de datos.
        """
        try:
            datos = json.dumps(
                cookies, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            fernet = cls._get_fernet()
            token = fernet.encrypt(datos)
            return base64.urlsafe_b64encode(token).decode("ascii")
        except (TypeError, ValueError) as e:
            logger.error(f"Serialization error: {e}")
            raise ValueError("Invalid cookie data format") from e
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            raise RuntimeError("Failed to encrypt cookies") from e

    @classmethod
    def _descifrar(cls, cookies_cifradas: str) -> dict | list:
        """
        Descifra las cookies desde la base de datos.
        """
        if not cookies_cifradas:
            raise ValueError("Empty encrypted cookies data")

        try:
            token = base64.urlsafe_b64decode(cookies_cifradas.encode("ascii"))
            fernet = cls._get_fernet()
            datos = fernet.decrypt(token)
            return json.loads(datos.decode("utf-8"))
        except (base64.binascii.Error, ValueError) as e:
            logger.error(f"Base64 decode error: {e}")
            raise ValueError("Invalid encrypted data format") from e
        except InvalidToken as e:
            logger.error(f"Invalid encryption token: {e}")
            raise ValueError("Corrupted or tampered session data") from e
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            raise ValueError("Invalid JSON data") from e
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise RuntimeError("Failed to decrypt cookies") from e

    @classmethod
    def exists(cls, proveedor: str) -> bool:
        """
        Verifica si existe una sesión para el proveedor.
        """
        if not proveedor or not proveedor.strip():
            return False

        proveedor = proveedor.upper().strip()

        try:
            if cls._cache().exists(RedisKeys.session(proveedor)):
                return True
        except Exception as e:
            logger.error(f"Cache error checking session existence for {proveedor}: {e}")

        try:
            return SesionProveedor.query.get(proveedor) is not None
        except SQLAlchemyError as e:
            logger.error(
                f"Database error checking session existence for {proveedor}: {e}"
            )
            return False

    @classmethod
    def refresh_cache(cls, proveedor: str) -> bool:
        """
        Refresca el cache desde la base de datos.
        """
        if not proveedor or not proveedor.strip():
            return False

        proveedor = proveedor.upper().strip()

        try:
            sesion = SesionProveedor.query.get(proveedor)
            if sesion is None or not sesion.cookies:
                cls._cache().delete(RedisKeys.session(proveedor))
                return False

            cookies = cls._descifrar(sesion.cookies)
            cls._cache().set_json(RedisKeys.session(proveedor), cookies)
            logger.debug(f"Cache refreshed for {proveedor}")
            return True

        except Exception as e:
            logger.error(f"Failed to refresh cache for {proveedor}: {e}")
            return False

    @classmethod
    def obtener_registro(cls, proveedor: str) -> SesionProveedor | None:
        return SesionProveedor.query.get(proveedor.upper())
