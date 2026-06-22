from decimal import Decimal

from app.models.producto import Producto
from app.models.producto_proveedor import (
    ProductoProveedor,
    ExistenciaSucursal,
)


class ProveedoresBDService:
    @staticmethod
    def buscar_producto(
        nombre: str | None = None,
        sku: str | None = None,
    ) -> list[ProductoProveedor]:

        query = Producto.query.join(Producto.proveedor)

        if sku:
            query = query.filter(Producto.clave_producto.ilike(f"%{sku}%"))

        elif nombre:
            query = query.filter(Producto.descripcion.ilike(f"%{nombre}%"))

        else:
            return []

        productos_db = query.all()

        resultados = []

        for producto in productos_db:
            existencias = [
                ExistenciaSucursal(
                    sucursal=existencia.sucursal,
                    existencia=existencia.existencia,
                )
                for existencia in producto.existencias_sucursal
            ]

            resultados.append(
                ProductoProveedor(
                    proveedor=producto.proveedor.nombre,
                    nombre=producto.descripcion,
                    precio=Decimal(str(producto.precio)),
                    moneda=producto.moneda,
                    existencia=producto.existencia,
                    descuento=producto.descuento,
                    existencias_sucursal=existencias,
                    url=None,
                    url_imagen=None,
                )
            )

        return resultados
