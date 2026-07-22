from app.extensions import db
from .base import BaseModel


class ProveedorCredenciales(BaseModel):
    __tablename__ = "proveedor_credenciales"

    id_credenciales = db.Column(db.Integer, primary_key=True)
    id_proveedor = db.Column(
        db.Integer,
        db.ForeignKey("proveedor.id_proveedor"),
        nullable=False,
        unique=True,
    )
    credenciales = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)
    updated_by = db.Column(
        db.Integer, db.ForeignKey("usuario.id_usuario"), nullable=False
    )

    proveedor = db.relationship(
        "Proveedor",
        back_populates="credenciales",
    )

    usuario = db.relationship(
        "Usuario",
        back_populates="credenciales_proveedor",
    )
