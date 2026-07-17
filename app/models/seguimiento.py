from app.extensions import db
from .base import BaseModel


class Seguimiento(BaseModel):
    __tablename__ = "seguimiento"

    id_seguimiento = db.Column(db.Integer, primary_key=True)
    id_orden = db.Column(
        db.Integer, db.ForeignKey("orden.id_orden"), nullable=False, unique=True
    )
    frecuencia_horas = db.Column(db.Integer, nullable=False)
    ultimo_escaneo = db.Column(db.DateTime, nullable=True)
    proximo_escaneo = db.Column(db.DateTime, nullable=True)
    ultimo_correo = db.Column(db.DateTime, nullable=True)
    cambio_precio = db.Column(db.Boolean, default=True)
    sin_stock = db.Column(db.Boolean, default=True)
    mejor_oferta = db.Column(db.Boolean, default=False)
    diferencia_minima = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    activo = db.Column(db.Boolean, default=True)

    orden = db.relationship("Orden", back_populates="seguimiento")
