from app.services.proveedores.IngramService import IngramService


class SincronizacionService:
    @staticmethod
    def sincronizar():
        IngramService.actualizar_inventario()
