from flask import Blueprint


ventas_bp = Blueprint("ventas", __name__, url_prefix="/ventas")

@ventas_bp.get("/")
def dashboard():
    return "Bienvenido al dashboard de ventas"