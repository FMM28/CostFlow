from typing import Optional, Tuple
from sqlalchemy import and_
from decimal import Decimal
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.models.agrupacion import Agrupacion
from app.models.agrupacion_detalle import AgrupacionDetalle
from app.models.orden import Orden
from app.models.orden_detalle import OrdenDetalle


class AgrupacionService:
    @staticmethod
    def create(data: dict) -> Tuple[Optional[Agrupacion], Optional[str]]:

        id_orden = data.get("id_orden")
        tipo = data.get("tipo")
        detalles = data.get("detalles", [])

        if not id_orden:
            return None, "La orden es obligatoria."

        if not tipo:
            return None, "El tipo es obligatorio."

        if tipo.upper() not in ["AGRUPACION", "PAQUETE"]:
            return None, "El tipo debe ser 'AGRUPACION' o 'PAQUETE'."

        if not detalles:
            return None, "Debe seleccionar al menos un detalle."

        orden = Orden.query.get(id_orden)
        if not orden:
            return None, "La orden no existe."

        # Verificar que todos los detalles existan y pertenezcan a la orden
        detalles_bd = OrdenDetalle.query.filter(
            OrdenDetalle.id_detalle.in_(detalles), OrdenDetalle.id_orden == id_orden
        ).all()

        if len(detalles_bd) != len(detalles):
            return None, "Uno o más detalles no pertenecen a la orden."

        # Verificar que ninguno ya pertenezca a otra agrupación
        existentes = AgrupacionDetalle.query.filter(
            AgrupacionDetalle.id_detalle.in_(detalles)
        ).first()

        if existentes:
            return None, "Uno o más detalles ya pertenecen a otra agrupación."

        try:
            agrupacion = Agrupacion(id_orden=id_orden, tipo=tipo.upper())

            db.session.add(agrupacion)
            db.session.flush()

            for id_detalle in detalles:
                db.session.add(
                    AgrupacionDetalle(
                        id_agrupacion=agrupacion.id_agrupacion, id_detalle=id_detalle
                    )
                )

            db.session.commit()

            return agrupacion, None

        except Exception as e:
            db.session.rollback()
            return None, str(e)

    @staticmethod
    def get_by_id(id_agrupacion: int) -> Tuple[Optional[Agrupacion], Optional[str]]:
        """Obtiene una agrupación por su ID"""
        try:
            agrupacion = Agrupacion.query.get(id_agrupacion)
            if not agrupacion:
                return None, "La agrupación no existe."
            return agrupacion, None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def get_orden_complete_details(
        id_orden: int,
    ) -> Tuple[Optional[dict], Optional[str]]:
        """
        Obtiene todas las agrupaciones de una orden con sus detalles completos
        y los detalles sueltos.
        """
        try:
            # 1. Verificar que la orden existe
            orden = Orden.query.get(id_orden)
            if not orden:
                return None, "La orden no existe."

            # Helper para serializar detalles
            def serialize_detalle(detalle):
                return {
                    "id_detalle": detalle.id_detalle,
                    "descripcion": detalle.producto,
                    "cantidad": detalle.cantidad,
                    "subtotal": detalle.subtotal,
                }

            # 2. Obtener todos los detalles de la orden en una sola consulta
            all_detalles = OrdenDetalle.query.filter_by(id_orden=id_orden).all()

            detalles_en_agrupacion_ids = set()
            agrupaciones_data = []

            # 3. Obtener agrupaciones con sus detalles y el OrdenDetalle relacionado
            #    precargados, para evitar N+1 queries.
            agrupaciones = (
                Agrupacion.query.filter_by(id_orden=id_orden)
                .options(
                    selectinload(Agrupacion.detalles).joinedload(
                        AgrupacionDetalle.detalle
                    )
                )
                .all()
            )

            # 4. Construir estructura de agrupaciones
            for agrupacion in agrupaciones:
                detalles_dict = []
                total_agrupacion = Decimal("0")

                for ad in agrupacion.detalles:
                    detalle = ad.detalle
                    if detalle is None:
                        # Detalle huérfano/eliminado; se ignora en vez de romper la respuesta.
                        continue

                    detalles_en_agrupacion_ids.add(detalle.id_detalle)

                    detalle_dict = serialize_detalle(detalle)
                    detalles_dict.append(detalle_dict)

                    total_agrupacion += detalle_dict["subtotal"] or Decimal("0")

                agrupaciones_data.append(
                    {
                        "id_agrupacion": agrupacion.id_agrupacion,
                        "descripcion": agrupacion.descripcion,
                        "informacion_adicional": agrupacion.informacion_adicional,
                        "tipo": agrupacion.tipo,
                        "detalles": detalles_dict,
                        "total_agrupacion": total_agrupacion,
                    }
                )

            # 5. Identificar detalles sueltos (no agrupados)
            detalles_sueltos_dict = [
                serialize_detalle(d)
                for d in all_detalles
                if d.id_detalle not in detalles_en_agrupacion_ids
            ]

            # 6. Construir estructura completa
            result = {
                "agrupaciones": agrupaciones_data,
                "detalles_sueltos": detalles_sueltos_dict,
            }

            return result, None

        except Exception as e:
            return None, str(e)

    @staticmethod
    def update(
        id_agrupacion: int, data: dict
    ) -> Tuple[Optional[Agrupacion], Optional[str]]:
        """
        Actualiza una agrupación
        """
        try:
            agrupacion = Agrupacion.query.get(id_agrupacion)
            if not agrupacion:
                return None, "La agrupación no existe."

            descripcion = data.get("descripcion")
            informacion_adicional = data.get("informacion_adicional")

            if descripcion is not None:
                agrupacion.descripcion = descripcion

            if informacion_adicional is not None:
                agrupacion.informacion_adicional = informacion_adicional

            db.session.commit()
            return agrupacion, None

        except Exception as e:
            db.session.rollback()
            return None, str(e)

    @staticmethod
    def delete(id_agrupacion: int) -> Tuple[bool, Optional[str]]:
        """Elimina una agrupación y todos sus detalles asociados"""
        try:
            agrupacion = Agrupacion.query.get(id_agrupacion)
            if not agrupacion:
                return False, "La agrupación no existe."

            # Los detalles se eliminarán automáticamente por cascade
            db.session.delete(agrupacion)
            db.session.commit()

            return True, None

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @staticmethod
    def add_detalle(id_agrupacion: int, id_detalle: int) -> Tuple[bool, Optional[str]]:
        """Agrega un detalle a una agrupación"""
        try:
            agrupacion = Agrupacion.query.get(id_agrupacion)
            if not agrupacion:
                return False, "La agrupación no existe."

            # Verificar que el detalle exista y pertenezca a la orden
            detalle = OrdenDetalle.query.filter(
                OrdenDetalle.id_detalle == id_detalle,
                OrdenDetalle.id_orden == agrupacion.id_orden,
            ).first()

            if not detalle:
                return False, "El detalle no existe o no pertenece a la orden."

            # Verificar que no pertenezca a otra agrupación
            existente = AgrupacionDetalle.query.filter_by(id_detalle=id_detalle).first()

            if existente:
                return False, "El detalle ya pertenece a otra agrupación."

            # Verificar que no esté ya en esta agrupación
            ya_existe = AgrupacionDetalle.query.filter(
                and_(
                    AgrupacionDetalle.id_agrupacion == id_agrupacion,
                    AgrupacionDetalle.id_detalle == id_detalle,
                )
            ).first()

            if ya_existe:
                return False, "El detalle ya pertenece a esta agrupación."

            db.session.add(
                AgrupacionDetalle(id_agrupacion=id_agrupacion, id_detalle=id_detalle)
            )
            db.session.commit()

            return True, None

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @staticmethod
    def delete_detalle(
        id_agrupacion: int, id_detalle: int
    ) -> Tuple[bool, Optional[str]]:
        """Elimina un detalle de una agrupación"""
        try:
            agrupacion = Agrupacion.query.get(id_agrupacion)
            if not agrupacion:
                return False, "La agrupación no existe."

            relacion = AgrupacionDetalle.query.filter(
                and_(
                    AgrupacionDetalle.id_agrupacion == id_agrupacion,
                    AgrupacionDetalle.id_detalle == id_detalle,
                )
            ).first()

            if not relacion:
                return False, "El detalle no pertenece a esta agrupación."

            db.session.delete(relacion)
            db.session.commit()

            return True, None

        except Exception as e:
            db.session.rollback()
            return False, str(e)
