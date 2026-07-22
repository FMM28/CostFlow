from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import ProveedorCredenciales, Proveedor
from app.security.crypto_service import CryptoService
from app.services.proveedor_service import ProveedorService

logger = logging.getLogger(__name__)


class ProveedorCredencialesService:
    @classmethod
    def obtener(cls, proveedor: str) -> dict[str, str] | None:
        """
        Obtiene las credenciales de un proveedor.
        """

        if not proveedor or not proveedor.strip():
            logger.warning("Empty proveedor provided")
            return None

        proveedor = proveedor.upper().strip()

        try:
            registro = (
                ProveedorCredenciales.query.join(Proveedor)
                .filter(Proveedor.nombre == proveedor)
                .first()
            )

            if registro is None:
                return None

            return CryptoService.decrypt_credentials(registro.credenciales)

        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving credentials for {proveedor}: {e}")
            return None

        except Exception as e:
            logger.error(
                f"Unexpected error retrieving credentials for {proveedor}: {e}"
            )
            return None

    @classmethod
    def guardar(
        cls,
        id_proveedor: int,
        credenciales: dict[str, str],
        updated_by: int,
    ) -> bool:
        """
        Crea o actualiza las credenciales de un proveedor.
        """

        proveedor = ProveedorService.get_by_id(id_proveedor)

        if proveedor is None:
            logger.warning(f"Proveedor {id_proveedor} not found")
            return False

        try:
            encrypted = CryptoService.encrypt_credentials(credenciales)

            registro = ProveedorCredenciales.query.filter_by(
                id_proveedor=id_proveedor
            ).first()

            now = datetime.now(timezone.utc)

            if registro is None:
                registro = ProveedorCredenciales(
                    id_proveedor=id_proveedor,
                    credenciales=encrypted,
                    updated_at=now,
                    updated_by=updated_by,
                )

                db.session.add(registro)

            else:
                registro.credenciales = encrypted
                registro.updated_at = now
                registro.updated_by = updated_by

            db.session.commit()

            return True

        except SQLAlchemyError as e:
            db.session.rollback()

            logger.error(
                f"Database error saving credentials for proveedor {id_proveedor}: {e}"
            )

            return False

        except Exception as e:
            db.session.rollback()

            logger.error(
                f"Unexpected error saving credentials for proveedor {id_proveedor}: {e}"
            )

            return False

    @classmethod
    def eliminar(cls, id_proveedor: int) -> bool:
        """
        Elimina las credenciales de un proveedor.
        """

        proveedor = ProveedorService.get_by_id(id_proveedor)

        if proveedor is None:
            logger.warning(f"Proveedor {id_proveedor} not found")
            return False

        try:
            registro = ProveedorCredenciales.query.filter_by(
                id_proveedor=id_proveedor
            ).first()

            if registro is None:
                return True

            db.session.delete(registro)
            db.session.commit()

            return True

        except SQLAlchemyError as e:
            db.session.rollback()

            logger.error(
                f"Database error deleting credentials for proveedor {id_proveedor}: {e}"
            )

            return False

        except Exception as e:
            db.session.rollback()

            logger.error(
                f"Unexpected error deleting credentials for proveedor {id_proveedor}: {e}"
            )

            return False

    @classmethod
    def existe(cls, id_proveedor: int) -> bool:
        """
        Verifica si existen credenciales para un proveedor.
        """

        proveedor = ProveedorService.get_by_id(id_proveedor)

        if proveedor is None:
            return False

        try:
            return (
                ProveedorCredenciales.query.filter_by(id_proveedor=id_proveedor).first()
                is not None
            )

        except SQLAlchemyError as e:
            logger.error(
                f"Database error checking credentials for proveedor {id_proveedor}: {e}"
            )
            return False
