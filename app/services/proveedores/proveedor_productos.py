from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.producto_proveedor import ProductoProveedor


class ProveedorProductos(ABC):

    @staticmethod
    @abstractmethod
    def buscar_producto(
        self,
        texto: str,
    ) -> ProductoProveedor:
        raise NotImplementedError