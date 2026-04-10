from flask import Blueprint, render_template


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.get("/")
def dashboard():
    return "Bienvenido al dashboard de administración"