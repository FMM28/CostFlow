from flask import Blueprint
from app.routes.ventas import ordenes


# Blueprint principal
ventas_bp = Blueprint("ventas", __name__, url_prefix="/ventas")

ventas_bp.register_blueprint(ordenes.ordenes_bp, url_prefix="/ordenes")
