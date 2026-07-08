from math import ceil
from pathlib import Path

from flask import current_app

from app.models.cotizacion import (
    Cotizacion,
    DetalleCotizacion,
    PaginaCotizacion,
    VendedorCotizacion,
)
from app.models.orden import Orden


class CotizacionMapper:
    MESES = (
        "",
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    )

    # mm disponibles para la tabla
    ALTURA_PAGINA = 138
    ALTURA_ULTIMA = 110

    # estimaciones
    ALTURA_BASE = 3
    ALTURA_LINEA = 4
    ALTURA_IMAGEN = 22

    CARACTERES_POR_LINEA = 58

    @classmethod
    def formatear_fecha(cls, fecha):

        if fecha is None:
            return None

        return f"{fecha.day:02d}-{cls.MESES[fecha.month]}-{fecha.year}"

    @classmethod
    def _contar_lineas(cls, texto):

        if not texto:
            return 0

        lineas = 0

        for linea in texto.splitlines():

            linea = linea.strip()

            if not linea:
                lineas += 1
                continue

            lineas += ceil(len(linea) / cls.CARACTERES_POR_LINEA)

        return lineas

    @classmethod
    def _altura_detalle(cls, detalle, incluir_imagenes):

        altura = cls.ALTURA_BASE

        altura += (
            cls._contar_lineas(detalle.descripcion)
            * cls.ALTURA_LINEA
        )

        altura += (
            cls._contar_lineas(detalle.informacion_adicional)
            * cls.ALTURA_LINEA
        )

        if incluir_imagenes and detalle.imagen:
            altura += cls.ALTURA_IMAGEN

        return altura

    @classmethod
    def paginar(cls, detalles, incluir_imagenes):

        paginas = []

        pagina_actual = []
        altura_actual = 0

        for detalle in detalles:

            altura = cls._altura_detalle(
                detalle,
                incluir_imagenes,
            )

            if (
                pagina_actual
                and altura_actual + altura > cls.ALTURA_PAGINA
            ):

                paginas.append(pagina_actual)
                pagina_actual = []
                altura_actual = 0

            pagina_actual.append(detalle)
            altura_actual += altura

        if pagina_actual or not paginas:
            paginas.append(pagina_actual)


        while True:

            altura_ultima = sum(
                cls._altura_detalle(
                    d,
                    incluir_imagenes,
                )
                for d in paginas[-1]
            )

            if altura_ultima <= cls.ALTURA_ULTIMA:
                break

            if len(paginas) == 1:
                paginas.insert(0, [])
                continue

            ultimo = paginas[-2].pop()

            paginas[-1].insert(
                0,
                ultimo,
            )

            if not paginas[-2]:
                paginas.pop(-2)

            altura_penultima = sum(
                cls._altura_detalle(
                    d,
                    incluir_imagenes,
                )
                for d in paginas[-2]
            )

            if altura_penultima > cls.ALTURA_PAGINA:

                paginas.insert(
                    -1,
                    [paginas[-2].pop()],
                )

        total = len(paginas)

        return [
            PaginaCotizacion(
                detalles=pagina,
                numero=i,
                total_paginas=total,
                ultima=i == total,
            )
            for i, pagina in enumerate(
                paginas,
                start=1,
            )
        ]

    @staticmethod
    def _static_uri(*parts):
        return (
            Path(current_app.static_folder)
            .joinpath(*parts)
            .resolve()
            .as_uri()
        )

    @classmethod
    def from_orden(cls, orden: Orden) -> Cotizacion:

        info = orden.informacion_adicional or {}

        vendedor = VendedorCotizacion(
            nombre=" ".join(
                filter(
                    None,
                    [
                        orden.usuario.nombre,
                        orden.usuario.ap_paterno,
                        orden.usuario.ap_materno,
                    ],
                )
            ),
            puesto=orden.usuario.puesto,
            telefono=orden.usuario.numero,
            correo=orden.usuario.email,
            firma=(
                str(orden.usuario.url_firma)
                if orden.incluir_firma and orden.usuario.url_firma
                else None
            ),
        )

        detalles = []

        for indice, detalle in enumerate(
            orden.detalles,
            start=1,
        ):
            detalles.append(
                DetalleCotizacion(
                    partida=indice,
                    cantidad=detalle.cantidad,
                    descripcion=detalle.producto,
                    imagen=detalle.url_imagen,
                    informacion_adicional=detalle.informacion_adicional,
                    precio_unitario=detalle.precio_venta,
                    total=detalle.subtotal,
                )
            )

        terminos = ""

        if orden.terminos_condiciones:
            terminos = " | ".join(
                linea.strip()
                for linea in orden.terminos_condiciones.splitlines()
                if linea.strip()
            )

        return Cotizacion(
            clave=orden.clave_orden,
            comprador=orden.comprador,
            fecha=cls.formatear_fecha(
                orden.fecha_creacion,
            ),
            vigencia=cls.formatear_fecha(
                orden.vigencia,
            ),
            subtotal=orden.subtotal,
            iva=orden.iva,
            total=orden.total,
            es_unam=orden.tipo_cotizacion == "UNAM",
            departamento=info.get("departamento"),
            solicitud_unam=info.get("no_solicitud"),
            proveedor_unam=info.get("proveedor_unam"),
            incluir_firma=orden.incluir_firma,
            incluir_imagenes=orden.incluir_imagenes,
            terminos=terminos,
            vendedor=vendedor,
            paginas=cls.paginar(
                detalles,
                orden.incluir_imagenes,
            ),
            logo_path=CotizacionMapper._static_uri(
                current_app.config.get(
                    "URL_LOGO_ARP"
                )
            ),
        )