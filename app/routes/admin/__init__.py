from flask import Blueprint
from app.routes.admin import dashboard, users, ordenes, proveedores, unam

# Blueprint principal
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Registrar todos los sub-blueprints en el principal
admin_bp.register_blueprint(dashboard.dashboard_bp)
admin_bp.register_blueprint(users.users_bp, url_prefix="/users")
admin_bp.register_blueprint(ordenes.ordenes_bp, url_prefix="/ordenes")
admin_bp.register_blueprint(proveedores.proveedores_bp, url_prefix="/proveedores")
admin_bp.register_blueprint(unam.unam_bp, url_prefix="/unam")
