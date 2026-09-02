import logging

import click

from app.services.sincronizacion_service import SincronizacionService
from app.services.seguimiento_monitor_service import SeguimientoMonitorService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)


def register_commands(app):

    @app.cli.command("sync-proveedores")
    def sync_proveedores():
        """Sincroniza los proveedores automáticos."""

        logger.info("Iniciando sincronización de proveedores...")

        try:
            SincronizacionService.sincronizar()
            logger.info("Sincronización de proveedores finalizada correctamente.")
            click.echo("Sincronización finalizada.")

        except Exception:
            logger.exception("Error durante la sincronización de proveedores.")
            raise

    @app.cli.command("monitorear-ordenes")
    def monitorear_ordenes():
        """Revisa los seguimientos pendientes y envía notificaciones."""

        logger.info("Iniciando monitoreo de órdenes...")

        try:
            SeguimientoMonitorService.procesar()
            logger.info("Monitoreo de órdenes finalizado correctamente.")
            click.echo("Monitoreo finalizado.")

        except Exception:
            logger.exception("Error durante el monitoreo de órdenes.")
            raise
        
    @app.cli.command("crear-admin")
    def crear_admin():
        """Crea el usuario administrador inicial."""
        click.echo("=== Creación del administrador inicial ===")
        click.echo()
        username = click.prompt("Nombre de usuario")
        email = click.prompt("Email")
        nombre = click.prompt("Nombre")
        ap_paterno = click.prompt("Apellido paterno")
        ap_materno = click.prompt(
            "Apellido materno",
            default="",
            show_default=False,
        )
        password = click.prompt(
            "Contraseña",
            hide_input=True,
            confirmation_prompt="Confirmar contraseña",
        )
        usuario, error = UserService.create(
            username=username,
            email=email,
            numero=None,
            puesto=None,
            url_firma=None,
            role="admin",
            nombre=nombre,
            ap_paterno=ap_paterno,
            ap_materno=ap_materno or None,
            password=password,
        )
        if error:
            raise click.ClickException(error)
        click.echo()
        click.echo(
            f"Administrador creado correctamente "
            f"(id={usuario.id_usuario}, username='{usuario.username}')."
        )
