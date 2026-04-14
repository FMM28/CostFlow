from flask import Flask
from .config import Config
from .extensions import db, migrate, bcrypt, login_manager
from app import models
from app.auth.login_manager import load_user
from app.logging_config import setup_logging
from .routes import register_blueprints

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    setup_logging(app)

    register_blueprints(app)

    return app