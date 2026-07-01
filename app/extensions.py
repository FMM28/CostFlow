from flask import current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from redis import Redis

db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = (
    "Tu sesión ha expirado. Por favor inicia sesión nuevamente."
)

def init_redis(app):
    redis = Redis(
        host=app.config["REDIS_HOST"],
        port=app.config["REDIS_PORT"],
        db=app.config["REDIS_DB"],
        password=app.config["REDIS_PASSWORD"],
        decode_responses=True,
    )

    try:
        redis.ping()
    except Exception as e:
        raise RuntimeError(f"Redis no disponible: {e}")

    app.extensions["redis"] = redis


def get_redis():
    return current_app.extensions["redis"]
