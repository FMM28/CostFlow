import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logging(app) -> None:
    """
    Configura el sistema de logging para la aplicación Flask.

    Args:
        app: Instancia de la aplicación Flask
    """
    # Obtener configuración con valores por defecto
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO"), logging.INFO)
    log_file = app.config.get("LOG_FILE", "app.log")
    log_max_bytes = app.config.get(
        "LOG_MAX_BYTES", 10 * 1024 * 1024
    )  # 10 MB por defecto
    log_backup_count = app.config.get("LOG_BACKUP_COUNT", 5)

    # Crear directorio de logs si no existe
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Formateador detallado para archivo
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] [%(module)s.%(funcName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Formateador más simple para consola
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s", datefmt="%H:%M:%S"
    )

    # Handler para archivo con rotación
    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=log_max_bytes,
            backupCount=log_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)  # Archivo guarda todo
    except (OSError, PermissionError) as e:
        # Si no se puede crear el archivo de log, continuar sin él
        print(f"No se pudo crear el archivo de log '{log_file}': {e}")
        file_handler = None

    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)  # Consola respeta el nivel configurado

    # Configurar logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # El logger raíz acepta todos los niveles

    # Limpiar handlers existentes para evitar duplicados
    root_logger.handlers.clear()

    # Agregar handlers
    if file_handler:
        root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Configurar loggers específicos
    _configure_specific_loggers(root_logger)

    # Suprimir logs muy verbosos de bibliotecas externas
    _configure_third_party_loggers()

    # Log de inicio
    app.logger.info(
        f"Logging configurado: nivel={logging.getLevelName(log_level)}, archivo={log_file}"
    )

    # Registrar excepciones no capturadas
    _setup_exception_logging()


def _configure_specific_loggers(root_logger: logging.Logger) -> None:
    """Configura niveles específicos para loggers de la aplicación."""
    # Logger de SQLAlchemy - solo mostrar warnings y errores en producción
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    # Logger de Flask - mantener en INFO
    logging.getLogger("flask").setLevel(logging.INFO)

    # Logger de Werkzeug (servidor de desarrollo)
    logging.getLogger("werkzeug").setLevel(logging.INFO)


def _configure_third_party_loggers() -> None:
    """Suprime logs muy verbosos de bibliotecas de terceros."""
    # Lista de loggers a suprimir o reducir
    quiet_loggers = [
        "urllib3",
        "requests",
        "boto3",
        "botocore",
    ]

    for logger_name in quiet_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _setup_exception_logging() -> None:
    """Configura el logging de excepciones no capturadas."""

    def handle_exception(exc_type, exc_value, exc_traceback):
        """Handler para excepciones no capturadas."""
        if issubclass(exc_type, KeyboardInterrupt):
            # No loguear KeyboardInterrupt
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logging.critical(
            "Excepción no capturada", exc_info=(exc_type, exc_value, exc_traceback)
        )

    import sys

    sys.excepthook = handle_exception


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger configurado para un módulo específico.

    Args:
        name: Nombre del logger (generalmente __name__)

    Returns:
        logging.Logger: Logger configurado
    """
    return logging.getLogger(name)


class RequestFormatter(logging.Formatter):
    """Formateador personalizado que incluye información de la request."""

    def format(self, record):
        from flask import has_request_context, request

        if has_request_context():
            record.url = request.url
            record.method = request.method
            record.remote_addr = request.remote_addr
            record.user_agent = (
                request.user_agent.string[:100] if request.user_agent else "Unknown"
            )
        else:
            record.url = None
            record.method = None
            record.remote_addr = None
            record.user_agent = None

        return super().format(record)


def setup_request_logging(app) -> None:
    """
    Configura logging específico para requests HTTP.

    Args:
        app: Instancia de la aplicación Flask
    """

    @app.before_request
    def log_request_info():
        """Log información básica de cada request."""
        from flask import request

        app.logger.debug(
            f"Request: {request.method} {request.path} "
            f"[IP: {request.remote_addr}] "
            f"[User-Agent: {request.user_agent.string[:50] if request.user_agent else 'Unknown'}]"
        )

    @app.after_request
    def log_response_info(response):
        """Log información de la respuesta."""
        from flask import request

        app.logger.debug(
            f"Response: {request.method} {request.path} "
            f"[Status: {response.status_code}]"
        )
        return response

    @app.errorhandler(Exception)
    def handle_exception(error):
        """Log excepciones no manejadas en las rutas."""
        from flask import request

        app.logger.error(
            f"Error en ruta {request.method} {request.path}: {str(error)}",
            exc_info=True,
        )

        raise error
