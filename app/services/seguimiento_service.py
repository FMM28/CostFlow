from datetime import datetime, timedelta
import logging
from typing import Optional, List

from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.models.seguimiento import Seguimiento
from app.models.orden import Orden

logger = logging.getLogger(__name__)


class SeguimientoService:
    """Servicio para gestionar el seguimiento de órdenes"""

    FRECUENCIA_MINIMA_HORAS = 1
    FRECUENCIA_MAXIMA_HORAS = 720

    @staticmethod
    def obtener_por_id(id_seguimiento: int) -> Optional[Seguimiento]:
        """
        Obtiene un seguimiento por su ID.
        """
        try:
            return Seguimiento.query.get(id_seguimiento)
        except SQLAlchemyError as e:
            logger.error(
                f"Error al obtener seguimiento por ID {id_seguimiento}: {str(e)}"
            )
            raise RuntimeError(
                f"Error de base de datos al obtener seguimiento: {str(e)}"
            )

    @staticmethod
    def obtener_por_orden(id_orden: int) -> Optional[Seguimiento]:
        """
        Obtiene el seguimiento de una orden específica.
        """
        try:
            return Seguimiento.query.filter_by(id_orden=id_orden).first()
        except SQLAlchemyError as e:
            logger.error(
                f"Error al obtener seguimiento para orden {id_orden}: {str(e)}"
            )
            raise RuntimeError(
                f"Error de base de datos al obtener seguimiento: {str(e)}"
            )

    @staticmethod
    def crear(id_orden: int) -> Seguimiento:
        """
        Crea un nuevo seguimiento para una orden.
        """
        try:
            # Verificar que la orden existe
            orden = Orden.query.get(id_orden)
            if not orden:
                logger.warning(
                    f"Intento de crear seguimiento para orden inexistente: {id_orden}"
                )
                raise ValueError(f"No se encontró la orden con ID {id_orden}")

            # Verificar que no exista seguimiento previo
            if SeguimientoService.obtener_por_orden(id_orden):
                logger.warning(
                    f"Intento de crear seguimiento duplicado para orden {id_orden}"
                )
                raise ValueError(f"La orden {id_orden} ya cuenta con un seguimiento")

            ahora = datetime.now()
            frecuencia_horas = SeguimientoService.FRECUENCIA_MINIMA_HORAS

            seguimiento = Seguimiento(
                id_orden=id_orden,
                frecuencia_horas=frecuencia_horas,
                ultimo_escaneo=None,
                proximo_escaneo=ahora + timedelta(hours=frecuencia_horas),
                ultimo_correo=None,
                activo=True,
            )

            db.session.add(seguimiento)
            db.session.commit()

            return seguimiento

        except (ValueError, SQLAlchemyError) as e:
            db.session.rollback()
            if isinstance(e, ValueError):
                raise
            logger.error(f"Error al crear seguimiento para orden {id_orden}: {str(e)}")
            raise RuntimeError(f"Error de base de datos al crear seguimiento: {str(e)}")

    @staticmethod
    def actualizar(
        id_seguimiento: int,
        frecuencia_horas: Optional[int] = None,
        cambio_precio: Optional[bool] = None,
        sin_stock: Optional[bool] = None,
        mejor_oferta: Optional[bool] = None,
        diferencia_minima: Optional[float] = None,
        activo: Optional[bool] = None,
    ) -> Seguimiento:
        """
        Actualiza un seguimiento existente.
        """
        try:
            seguimiento = SeguimientoService.obtener_por_id(id_seguimiento)
            if not seguimiento:
                logger.warning(f"Seguimiento no encontrado con ID: {id_seguimiento}")
                raise ValueError(
                    f"No se encontró el seguimiento con ID {id_seguimiento}"
                )

            # Validar frecuencia
            if frecuencia_horas is not None:
                if frecuencia_horas < SeguimientoService.FRECUENCIA_MINIMA_HORAS:
                    raise ValueError(
                        f"La frecuencia mínima es de {SeguimientoService.FRECUENCIA_MINIMA_HORAS} hora(s)"
                    )
                if frecuencia_horas > SeguimientoService.FRECUENCIA_MAXIMA_HORAS:
                    raise ValueError(
                        f"La frecuencia máxima es de {SeguimientoService.FRECUENCIA_MAXIMA_HORAS} horas"
                    )
                seguimiento.frecuencia_horas = frecuencia_horas

                # Recalcular próximo escaneo si está activo
                if seguimiento.activo and seguimiento.ultimo_escaneo:
                    seguimiento.proximo_escaneo = (
                        seguimiento.ultimo_escaneo + timedelta(hours=frecuencia_horas)
                    )

            # Actualizar campos
            if cambio_precio is not None:
                seguimiento.cambio_precio = cambio_precio
            if sin_stock is not None:
                seguimiento.sin_stock = sin_stock
            if mejor_oferta is not None:
                seguimiento.mejor_oferta = mejor_oferta
            if diferencia_minima is not None:
                if diferencia_minima < 0:
                    raise ValueError("La diferencia mínima no puede ser negativa")
                seguimiento.diferencia_minima = diferencia_minima
            if activo is not None:
                seguimiento.activo = activo
                if activo and not seguimiento.proximo_escaneo:
                    seguimiento.proximo_escaneo = datetime.now() + timedelta(
                        hours=seguimiento.frecuencia_horas
                    )

            db.session.commit()
            return seguimiento

        except ValueError:
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error al actualizar seguimiento {id_seguimiento}: {str(e)}")
            raise RuntimeError(
                f"Error de base de datos al actualizar seguimiento: {str(e)}"
            )

    @staticmethod
    def eliminar(id_seguimiento: int) -> None:
        """
        Elimina un seguimiento.
        """
        try:
            seguimiento = SeguimientoService.obtener_por_id(id_seguimiento)
            if not seguimiento:
                logger.warning(f"Seguimiento no encontrado con ID: {id_seguimiento}")
                raise ValueError(
                    f"No se encontró el seguimiento con ID {id_seguimiento}"
                )

            db.session.delete(seguimiento)
            db.session.commit()
        except ValueError:
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error al eliminar seguimiento {id_seguimiento}: {str(e)}")
            raise RuntimeError(
                f"Error de base de datos al eliminar seguimiento: {str(e)}"
            )

    @staticmethod
    def activar(id_seguimiento: int) -> Seguimiento:
        """
        Activa un seguimiento.
        """
        try:
            seguimiento = SeguimientoService.obtener_por_id(id_seguimiento)
            if not seguimiento:
                logger.warning(f"Seguimiento no encontrado con ID: {id_seguimiento}")
                raise ValueError(
                    f"No se encontró el seguimiento con ID {id_seguimiento}"
                )

            if not seguimiento.activo:
                seguimiento.activo = True
                if seguimiento.proximo_escaneo is None:
                    seguimiento.proximo_escaneo = datetime.now() + timedelta(
                        hours=seguimiento.frecuencia_horas
                    )
                db.session.commit()

            return seguimiento
        except ValueError:
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error al activar seguimiento {id_seguimiento}: {str(e)}")
            raise RuntimeError(
                f"Error de base de datos al activar seguimiento: {str(e)}"
            )

    @staticmethod
    def desactivar(id_seguimiento: int) -> Seguimiento:
        """
        Desactiva un seguimiento.
        """
        try:
            seguimiento = SeguimientoService.obtener_por_id(id_seguimiento)
            if not seguimiento:
                logger.warning(f"Seguimiento no encontrado con ID: {id_seguimiento}")
                raise ValueError(
                    f"No se encontró el seguimiento con ID {id_seguimiento}"
                )

            if seguimiento.activo:
                seguimiento.activo = False
                db.session.commit()

            return seguimiento
        except ValueError:
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Error al desactivar seguimiento {id_seguimiento}: {str(e)}")
            raise RuntimeError(
                f"Error de base de datos al desactivar seguimiento: {str(e)}"
            )

    @staticmethod
    def obtener_pendientes() -> List[Seguimiento]:
        """
        Obtiene todos los seguimientos pendientes de escanear.
        """
        try:
            pendientes = (
                Seguimiento.query.join(Orden)
                .filter(
                    Seguimiento.activo.is_(True),
                    Seguimiento.proximo_escaneo <= datetime.now(),
                    Orden.estado == "pendiente",
                )
                .order_by(Seguimiento.proximo_escaneo)
                .all()
            )
            return pendientes
        except SQLAlchemyError as e:
            logger.error(f"Error al obtener seguimientos pendientes: {str(e)}")
            raise RuntimeError(
                f"Error de base de datos al obtener pendientes: {str(e)}"
            )

    @staticmethod
    def registrar_escaneo(
        id_seguimiento: int,
        correo_enviado: bool = False,
    ) -> Seguimiento:
        """
        Registra un nuevo escaneo para un seguimiento.
        """
        try:
            seguimiento = SeguimientoService.obtener_por_id(id_seguimiento)
            if not seguimiento:
                logger.warning(f"Seguimiento no encontrado con ID: {id_seguimiento}")
                raise ValueError(
                    f"No se encontró el seguimiento con ID {id_seguimiento}"
                )

            ahora = datetime.now()
            seguimiento.ultimo_escaneo = ahora

            if seguimiento.activo:
                seguimiento.proximo_escaneo = ahora + timedelta(
                    hours=seguimiento.frecuencia_horas
                )
            else:
                seguimiento.proximo_escaneo = None

            if correo_enviado:
                seguimiento.ultimo_correo = ahora

            db.session.commit()

            return seguimiento
        except ValueError:
            raise
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(
                f"Error al registrar escaneo para seguimiento {id_seguimiento}: {str(e)}"
            )
            raise RuntimeError(f"Error de base de datos al registrar escaneo: {str(e)}")
