from app.extensions import db
from .base import BaseModel


class Agrupacion(BaseModel):
    __tablename__ = "agrupacion"

    id_agrupacion = db.Column(db.Integer, primary_key=True)
    id_orden = db.Column(db.Integer, db.ForeignKey("orden.id_orden"), nullable=False)
    descripcion = db.Column(db.String(150), nullable=True)
    informacion_adicional = db.Column(db.Text, nullable=True)
    tipo = db.Column(db.String(20), nullable=False)

    orden = db.relationship("Orden", back_populates="agrupaciones")
    detalles = db.relationship(
        "AgrupacionDetalle", back_populates="agrupacion", cascade="all, delete-orphan"
    )
