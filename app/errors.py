import logging

from flask import jsonify, render_template, request
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.extensions import db

logger = logging.getLogger(__name__)


def _is_api_request() -> bool:
    """
    Determina si la respuesta debe devolverse como JSON.
    """
    if request.path.startswith("/api"):
        return True

    if request.accept_mimetypes.best == "application/json":
        return True

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True

    return False


def _json_error(message: str, status: int):
    return (
        jsonify(
            {
                "success": False,
                "status": status,
                "message": message,
            }
        ),
        status,
    )


def _log_exception(error: Exception):
    """
    Registra información útil para diagnosticar errores.
    """

    logger.exception(
        "Excepción no controlada | %s %s | IP=%s | Usuario=%s",
        request.method,
        request.full_path,
        request.remote_addr,
        getattr(getattr(request, "user", None), "id", None),
        exc_info=error,
    )


def register_error_handlers(app):
    """
    Registra todos los manejadores de errores de la aplicación.
    """

    @app.errorhandler(400)
    def bad_request(error):
        if _is_api_request():
            return _json_error("Solicitud inválida.", 400)

        return render_template("errors/400.html"), 400

    @app.errorhandler(401)
    def unauthorized(error):
        if _is_api_request():
            return _json_error("No autenticado.", 401)

        return render_template("errors/401.html"), 401

    @app.errorhandler(403)
    def forbidden(error):
        if _is_api_request():
            return _json_error("No tienes permisos para realizar esta acción.", 403)

        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        if _is_api_request():
            return _json_error("Recurso no encontrado.", 404)

        return render_template("errors/404.html"), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        if _is_api_request():
            return _json_error("Método no permitido.", 405)

        return render_template("errors/405.html"), 405

    @app.errorhandler(413)
    def request_entity_too_large(error):
        if _is_api_request():
            return _json_error("El archivo excede el tamaño permitido.", 413)

        return render_template("errors/413.html"), 413

    @app.errorhandler(429)
    def too_many_requests(error):
        if _is_api_request():
            return _json_error("Demasiadas solicitudes.", 429)

        return render_template("errors/429.html"), 429

    @app.errorhandler(SQLAlchemyError)
    def sqlalchemy_error(error):
        """
        Cualquier excepción de SQLAlchemy deja la sesión en estado inválido.
        Siempre debe hacerse rollback.
        """
        db.session.rollback()

        _log_exception(error)

        if _is_api_request():
            return _json_error(
                "Ocurrió un error al acceder a la base de datos.",
                500,
            )

        return render_template("errors/500.html"), 500

    @app.errorhandler(Exception)
    def handle_exception(error):
        """
        Manejador global para cualquier excepción no controlada.
        """

        if isinstance(error, HTTPException):
            return error

        try:
            db.session.rollback()
        except Exception:
            pass

        _log_exception(error)

        if _is_api_request():
            return _json_error(
                "Ha ocurrido un error interno del servidor.",
                500,
            )

        return render_template("errors/500.html"), 500
