from app.extensions import db
from .base import BaseModel

class Orden(BaseModel):
    __tablename__ = "orden"

    id_orden = db.Column(db.Integer, primary_key=True)
    clave_orden = db.Column(db.String(45), unique=True, nullable=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuario.id_usuario"), nullable=False)
    comprador = db.Column(db.String(150), nullable=False)
    fecha_creacion = db.Column(db.Date, default=db.func.now())
    vigencia = db.Column(db.Date, nullable=True)
    tipo_cotizacion = db.Column(db.String(20), nullable=True)
    informacion_adicional = db.Column(db.JSON, nullable=True)
    estado = db.Column(db.String(20), default="pendiente")
    subtotal = db.Column(db.Numeric(10, 2), default=0)
    iva = db.Column(db.Numeric(10, 2), default=0)
    total = db.Column(db.Numeric(10, 2), default=0)
    terminos_condiciones = db.Column(db.Text, nullable=True)
    incluir_firma = db.Column(db.Boolean, default=False)
    incluir_imagenes = db.Column(db.Boolean, default=False)

    usuario  = db.relationship("Usuario", back_populates="ordenes")
    detalles = db.relationship("OrdenDetalle", back_populates="orden", cascade="all, delete-orphan")