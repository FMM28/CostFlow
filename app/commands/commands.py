import click

from app.services.sincronizacion_service import SincronizacionService


def register_commands(app):

    @app.cli.command("sync-proveedores")
    def sync_proveedores():
        """Sincroniza los proveedores automáticos."""
        SincronizacionService.sincronizar()
        click.echo("Sincronización finalizada.")
