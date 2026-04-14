from app.extensions import db
from .base import BaseModel

class OrdenDetalle(BaseModel):
    __tablename__ = "orden_detalle"

    id_detalle = db.Column(db.Integer, primary_key=True)
    id_orden = db.Column(db.Integer, db.ForeignKey("orden.id_orden"), nullable=False)
    id_proveedor = db.Column(db.Integer, db.ForeignKey("proveedor.id_proveedor"), nullable=True)
    producto = db.Column(db.String(255), nullable=False)
    clave_producto = db.Column(db.String(100), nullable=True)   # SKU
    url_producto = db.Column(db.String(500), nullable=True)
    url_imagen = db.Column(db.String(500), nullable=True)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)  # Costo de compra
    costo_envio = db.Column(db.Numeric(10, 2), nullable=False, default=0) # Costo de envío por pieza
    ganancia_unitaria = db.Column(db.Numeric(10, 2), nullable=False, default=0)  # Margen por pieza
    precio_venta = db.Column(db.Numeric(10, 2), nullable=False)  # precio_unitario + ganancia
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)  # precio_venta * cantidad

    orden     = db.relationship("Orden", back_populates="detalles")
    proveedor = db.relationship("Proveedor", back_populates="detalles")