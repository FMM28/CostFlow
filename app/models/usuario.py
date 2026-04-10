from app.extensions import db, bcrypt
from .base import BaseModel
from flask_login import UserMixin

class Usuario(UserMixin,BaseModel):
    __tablename__ = "usuario"

    id_usuario = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(45), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    ap_paterno = db.Column(db.String(45), nullable=False)
    ap_materno = db.Column(db.String(45), nullable=True)

    def set_password(self, raw_password):
        self.password = bcrypt.generate_password_hash(
            raw_password
        ).decode("utf-8")

    def check_password(self, raw_password):
        return bcrypt.check_password_hash(
            self.password,
            raw_password
        )

    def get_id(self):
        return str(self.id_usuario)
    
    @property
    def id(self):
        return self.id_usuario
