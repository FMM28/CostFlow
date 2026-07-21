from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import SesionProveedor
from app.cache.redis_cache import RedisCache
from app.cache.redis_keys import RedisKeys
from app.security.crypto_service import CryptoService

logger = logging.getLogger(__name__)


class SesionProveedorService:
    @classmethod
    def _cache(cls):
        return RedisCache()

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

            cookies = CryptoService.decrypt_session(sesion.cookies)

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
            encrypted_cookies = CryptoService.encrypt_session(cookies)
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
    def obtener_registro(cls, proveedor: str) -> SesionProveedor | None:
        return SesionProveedor.query.get(proveedor.upper())
