from app.extensions import db
from .base import BaseModel


class DepartamentoUNAM(BaseModel):
    __tablename__ = "departamento_unam"
    
    id_departamento = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(255), nullable=False, unique=True)
    prefijo = db.Column(db.String(8), nullable=False)
    puntos_entrega = db.Column(db.JSON, nullable=True)
    