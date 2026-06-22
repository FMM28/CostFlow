from app.extensions import db
from .base import BaseModel


class ExistenciaProducto(BaseModel):
    __tablename__ = "existencia_producto"

    id_existencia = db.Column(db.Integer, primary_key=True)
    id_producto = db.Column(
        db.Integer, db.ForeignKey("producto.id_producto"), nullable=False
    )
    sucursal = db.Column(db.String(50), nullable=False)
    existencia = db.Column(db.Integer, nullable=False)

    producto = db.relationship("Producto", back_populates="existencias_sucursal")
