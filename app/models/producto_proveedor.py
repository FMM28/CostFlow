from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(slots=True)
class ProductoProveedor:
    proveedor: str
    nombre: str
    precio: Decimal
    moneda: str
    existencia: Optional[int]
    url: Optional[str] = None
    url_imagen: Optional[str] = None