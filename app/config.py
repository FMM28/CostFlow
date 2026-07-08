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

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

    PRODUCTOS_CACHE_TTL = int(os.getenv("PRODUCTOS_CACHE_TTL", 300))

    TIPO_CAMBIO_CACHE_TTL = int(os.getenv("TIPO_CAMBIO_CACHE_TTL", 3600))

    SECRET_KEY = os.environ.get("SECRET_KEY")
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

    CVA_URL = os.getenv("CVA_URL")
    CVA_CLIENTE = os.getenv("CVA_CLIENTE")

    INGRAM_CLIENT_ID = os.getenv("INGRAM_CLIENT_ID")
    INGRAM_CLIENT_SECRET = os.getenv("INGRAM_CLIENT_SECRET")
    INGRAM_CUSTOMER_NUMBER = os.getenv("INGRAM_CUSTOMER_NUMBER")
    INGRAM_COUNTRY_CODE = os.getenv("INGRAM_COUNTRY_CODE")
    INGRAM_URL = os.getenv("INGRAM_URL")

    SYSCOM_URL = os.getenv("SYSCOM_URL")
    SYSCOM_CLIENT_ID = os.getenv("SYSCOM_CLIENT_ID")
    SYSCOM_CLIENT_SECRET = os.getenv("SYSCOM_CLIENT_SECRET")

    SICLIK_EMAIL = os.getenv("SICLIK_EMAIL")
    SICLIK_PASSWORD = os.getenv("SICLIK_PASSWORD")
    SICLIK_CUSTOMER_ID = os.getenv("SICLIK_CUSTOMER_ID")

    TECHSMART_RFC = os.getenv("TECHSMART_RFC")
    TECHSMART_USUARIO = os.getenv("TECHSMART_USUARIO")
    TECHSMART_PASSWORD = os.getenv("TECHSMART_PASSWORD")
    TECHSMART_URL = os.getenv("TECHSMART_URL")

    GLOMA_USUARIO = os.getenv("GLOMA_USUARIO")
    GLOMA_PASSWORD = os.getenv("GLOMA_PASSWORD")
    GLOMA_URL = os.getenv("GLOMA_URL")

    EXEL_USUARIO = os.getenv("EXEL_USUARIO")
    EXEL_PASSWORD = os.getenv("EXEL_PASSWORD")
