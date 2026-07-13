from app.extensions import db
from .base import BaseModel


class AgrupacionDetalle(BaseModel):
    __tablename__ = "agrupacion_detalle"

    id_agrupacion_detalle = db.Column(db.Integer, primary_key=True)
    id_agrupacion = db.Column(
        db.Integer, db.ForeignKey("agrupacion.id_agrupacion"), nullable=False
    )
    id_detalle = db.Column(
        db.Integer, db.ForeignKey("orden_detalle.id_detalle"), nullable=False
    )

    agrupacion = db.relationship("Agrupacion", back_populates="detalles")
    detalle = db.relationship("OrdenDetalle", back_populates="agrupaciones")
