import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:"
        f"{os.getenv('DB_PASSWORD')}@"
        f"{os.getenv('DB_HOST')}:"
        f"{os.getenv('DB_PORT')}/"
        f"{os.getenv('DB_NAME')}"
    )

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_reset_on_return": "rollback",
    }

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

    PRODUCTOS_CACHE_TTL = int(os.getenv("PRODUCTOS_CACHE_TTL", 300))

    TIPO_CAMBIO_CACHE_TTL = int(os.getenv("TIPO_CAMBIO_CACHE_TTL", 3600))

    SECRET_KEY = os.environ.get("SECRET_KEY")
    MASTER_ENCRYPTION_KEY = os.environ.get("MASTER_ENCRYPTION_KEY")
    WTF_CSRF_ENABLED = True

    LOG_LEVEL = "INFO"
    LOG_FILE = "app.log"
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT = 5

    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "app/static/uploads/firmas")

    ARP_NAME = os.getenv("ARP_NAME")
    URL_LOGO_ARP = os.getenv("URL_LOGO_ARP")
    RFC_ARP = os.getenv("RFC_ARP")
    DIRECCION_ARP = os.getenv("DIRECCION_ARP")

    MARGEN_CONVERSION = float(os.getenv("MARGEN_CONVERSION", 0))

    GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
    GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")

    CVA_URL = os.getenv("CVA_URL")
    SYSCOM_URL = os.getenv("SYSCOM_URL")
    TECHSMART_URL = os.getenv("TECHSMART_URL")
    GLOMA_URL = os.getenv("GLOMA_URL")
    PCH_URL = os.getenv("PCH_URL")
