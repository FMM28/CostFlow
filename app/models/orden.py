from app.extensions import db
from .base import BaseModel

class Orden(BaseModel):
    __tablename__ = "orden"

    id_orden = db.Column(db.Integer, primary_key=True)
    clave_orden = db.Column(db.String(45), unique=True, nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuario.id_usuario"), nullable=False)
    comprador = db.Column(db.String(150), nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=db.func.now())
    estado = db.Column(db.String(20), default="pendiente")
    subtotal = db.Column(db.Numeric(10, 2), default=0)
    iva = db.Column(db.Numeric(10, 2), default=0)
    total = db.Column(db.Numeric(10, 2), default=0)

    usuario  = db.relationship("Usuario", back_populates="ordenes")
    detalles = db.relationship("OrdenDetalle", back_populates="orden", cascade="all, delete-orphan")