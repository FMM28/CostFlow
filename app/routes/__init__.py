from .login import auth_bp
from .root import main_bp
from .admin import admin_bp
from .ventas import ventas_bp

def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ventas_bp)