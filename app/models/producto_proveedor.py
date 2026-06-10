from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass(slots=True)
class ExistenciaSucursal:
    sucursal: str
    existencia: int


@dataclass(slots=True)
class ProductoProveedor:
    proveedor: str
    nombre: str
    precio: Decimal
    moneda: str
    existencia: Optional[int]
    descuento: Optional[Decimal] = None
    existencias_sucursal: list[ExistenciaSucursal] = field(default_factory=list)
    url: Optional[str] = None
    url_imagen: Optional[str] = None