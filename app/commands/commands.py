import logging

import click

from app.services.sincronizacion_service import SincronizacionService
from app.services.seguimiento_monitor_service import SeguimientoMonitorService

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
