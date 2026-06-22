from app.extensions import db
from .base import BaseModel


class Producto(BaseModel):
    __tablename__ = "producto"

    id_producto = db.Column(db.Integer, primary_key=True)
    id_proveedor = db.Column(
        db.Integer, db.ForeignKey("proveedor.id_proveedor"), nullable=False
    )
    descripcion = db.Column(db.String(255), nullable=False)
    clave_producto = db.Column(db.String(100), nullable=False)  # SKU
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    descuento = db.Column(db.Numeric(10, 2), nullable=True)
    moneda = db.Column(db.String(3), nullable=False)
    existencia = db.Column(db.Integer, nullable=True)
    clave_interna = db.Column(db.String(100), nullable=True)
    actualizado_en = db.Column(db.DateTime, nullable=True)

    existencias_sucursal = db.relationship(
        "ExistenciaProducto",
        back_populates="producto",
        cascade="all, delete-orphan",
        lazy=True,
    )
    proveedor = db.relationship("Proveedor", back_populates="productos")
