from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(slots=True)
class VendedorCotizacion:
    nombre: str
    puesto: str | None
    telefono: str | None
    correo: str
    firma: str | None


@dataclass(slots=True)
class DetalleCotizacion:
    partida: int
    cantidad: int
    descripcion: str
    imagen: str | None
    informacion_adicional: str | None
    precio_unitario: Decimal
    total: Decimal


@dataclass(slots=True)
class PaginaCotizacion:
    detalles: list[DetalleCotizacion]
    numero: int
    total_paginas: int
    ultima: bool


@dataclass(slots=True)
class Cotizacion:
    logo_path: str
    clave: str
    comprador: str
    fecha: date
    vigencia: date | None
    subtotal: Decimal
    iva: Decimal
    total: Decimal
    es_unam: bool
    es_persona_fisica: bool
    departamento: str | None
    solicitud_unam: str | None
    proveedor_unam: str | None
    incluir_firma: bool
    incluir_imagenes: bool
    terminos: str | None
    vendedor: VendedorCotizacion
    paginas: list[PaginaCotizacion]
