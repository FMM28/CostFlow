from flask import Flask
from .config import Config
from .extensions import db, migrate, bcrypt, login_manager, csrf, init_redis
from app import models
from app.auth.login_manager import load_user
from app.logging_config import setup_logging
from .routes import register_blueprints
from app.commands.commands import register_commands
from app.errors import register_error_handlers
from app.security import configure_security_headers
from werkzeug.middleware.proxy_fix import ProxyFix


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    csrf.init_app(app)

    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_port=1,
    )

    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    init_redis(app)

    setup_logging(app)

    register_blueprints(app)
    register_commands(app)
    register_error_handlers(app)
    configure_security_headers(app)

    return app
