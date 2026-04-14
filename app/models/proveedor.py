from app.extensions import db
from .base import BaseModel

class Proveedor(BaseModel):
    __tablename__ = "proveedor"

    id_proveedor = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    detalles = db.relationship("OrdenDetalle", back_populates="proveedor", lazy=True)