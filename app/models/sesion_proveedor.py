from app.extensions import db
from .base import BaseModel

class SesionProveedor(BaseModel):
    __tablename__ = "sesion_proveedor"

    proveedor = db.Column(
        db.String(50),
        primary_key=True
    )

    cookies = db.Column(
        db.JSON,
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False
    )