from decimal import Decimal, ROUND_HALF_UP
import io
import logging
import tempfile
import uuid
from math import ceil
from pathlib import Path

import requests
from flask import current_app
from PIL import Image

from app.models.cotizacion import (
    Cotizacion,
    DetalleCotizacion,
    PaginaCotizacion,
    VendedorCotizacion,
)
from app.models.orden import Orden

logger = logging.getLogger(__name__)


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
    ALTURA_PAGINA = 135
    ALTURA_ULTIMA = 110

    # estimaciones
    ALTURA_BASE = 3
    ALTURA_LINEA = 4
    ALTURA_IMAGEN = 22

    CARACTERES_POR_LINEA = 58

    SEPARADOR_AGRUPACION = " / "
    SEPARADOR_PAQUETE = " + "

    # collage de imagenes agrupadas
    ALTURA_COLLAGE_PX = 300
    ESPACIADO_COLLAGE_PX = 8
    TIMEOUT_DESCARGA_IMAGEN = 10

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

        altura += cls._contar_lineas(detalle.descripcion) * cls.ALTURA_LINEA

        altura += cls._contar_lineas(detalle.informacion_adicional) * cls.ALTURA_LINEA

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

            if pagina_actual and altura_actual + altura > cls.ALTURA_PAGINA:
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
        return Path(current_app.static_folder).joinpath(*parts).resolve().as_uri()

    @classmethod
    def _descargar_imagen(cls, url):

        try:
            respuesta = requests.get(
                url,
                timeout=cls.TIMEOUT_DESCARGA_IMAGEN,
            )
            respuesta.raise_for_status()

            return Image.open(io.BytesIO(respuesta.content)).convert("RGB")

        except Exception as error:
            logger.warning(f"No se pudo descargar imagen para collage ({url}): {error}")
            return None

    @classmethod
    def _generar_collage(cls, urls):

        if not urls:
            return None

        imagenes = [
            imagen
            for imagen in (cls._descargar_imagen(url) for url in urls)
            if imagen is not None
        ]

        if not imagenes:
            logger.warning(
                "Collage: ninguna imagen se pudo descargar, no se genera collage."
            )
            return None

        alto = cls.ALTURA_COLLAGE_PX

        redimensionadas = []

        for imagen in imagenes:
            proporcion = alto / imagen.height
            ancho = max(
                1,
                round(imagen.width * proporcion),
            )
            redimensionadas.append(imagen.resize((ancho, alto)))

        ancho_total = sum(
            imagen.width for imagen in redimensionadas
        ) + cls.ESPACIADO_COLLAGE_PX * (len(redimensionadas) - 1)

        collage = Image.new(
            "RGB",
            (ancho_total, alto),
            "white",
        )

        x = 0

        for imagen in redimensionadas:
            collage.paste(imagen, (x, 0))
            x += imagen.width + cls.ESPACIADO_COLLAGE_PX

        try:
            directorio = Path(tempfile.gettempdir()) / "cotizacion_collages"
            directorio.mkdir(parents=True, exist_ok=True)

            ruta = directorio / f"{uuid.uuid4().hex}.png"
            collage.save(ruta, "PNG")

            return ruta.resolve().as_uri()

        except Exception as error:
            logger.error(f"Collage: fallo al guardar el archivo temporal: {error}")
            return None

    @staticmethod
    def _formatear_cantidad(cantidad):

        if cantidad == int(cantidad):
            return str(int(cantidad))

        return str(cantidad)

    @classmethod
    def _texto_articulo(cls, agrupacion_detalle):

        detalle = agrupacion_detalle.detalle
        cantidad = detalle.cantidad

        if cantidad and cantidad != 1:
            return f"{cls._formatear_cantidad(cantidad)} x {detalle.producto}"

        return detalle.producto

    @classmethod
    def _detalle_desde_agrupacion(cls, agrupacion, partida, es_persona_fisica=False):

        separador = (
            cls.SEPARADOR_PAQUETE
            if agrupacion.tipo == "PAQUETE"
            else cls.SEPARADOR_AGRUPACION
        )

        articulos = [
            cls._texto_articulo(agrupacion_detalle)
            for agrupacion_detalle in agrupacion.detalles
        ]

        descripcion = separador.join(articulos)

        if agrupacion.descripcion:
            descripcion = f"{agrupacion.descripcion} {descripcion}"

        if es_persona_fisica:
            total = Decimal("0.00")

            for agrupacion_detalle in agrupacion.detalles:
                detalle = agrupacion_detalle.detalle

                precio_unitario = (detalle.precio_venta * Decimal("1.16")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )

                total += precio_unitario * detalle.cantidad

            total = total.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        else:
            total = sum(
                (agrupacion_detalle.detalle.subtotal or Decimal("0.00"))
                for agrupacion_detalle in agrupacion.detalles
            )

        urls_imagenes = [
            agrupacion_detalle.detalle.url_imagen
            for agrupacion_detalle in agrupacion.detalles
            if agrupacion_detalle.detalle.url_imagen
        ]

        imagen = cls._generar_collage(urls_imagenes)

        return DetalleCotizacion(
            partida=partida,
            cantidad=1,
            descripcion=descripcion,
            imagen=imagen,
            informacion_adicional=agrupacion.informacion_adicional,
            precio_unitario=total,
            total=total,
        )

    @classmethod
    def _construir_detalles(cls, orden, es_persona_fisica=False):

        detalles_agrupados = {
            agrupacion_detalle.id_detalle
            for agrupacion in orden.agrupaciones
            for agrupacion_detalle in agrupacion.detalles
        }

        detalles = []
        partida = 1

        for detalle in orden.detalles:
            if detalle.id_detalle in detalles_agrupados:
                continue

            if es_persona_fisica:
                precio_unitario = (detalle.precio_venta * Decimal("1.16")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                total = precio_unitario * detalle.cantidad
            else:
                precio_unitario = detalle.precio_venta
                total = detalle.subtotal

            detalles.append(
                DetalleCotizacion(
                    partida=partida,
                    cantidad=detalle.cantidad,
                    descripcion=detalle.producto,
                    imagen=detalle.url_imagen,
                    informacion_adicional=detalle.informacion_adicional,
                    precio_unitario=precio_unitario,
                    total=total,
                )
            )
            partida += 1

        for agrupacion in orden.agrupaciones:
            detalles.append(
                cls._detalle_desde_agrupacion(
                    agrupacion,
                    partida,
                    es_persona_fisica,
                )
            )
            partida += 1

        return detalles

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

        es_persona_fisica = orden.tipo_cotizacion == "PERSONA FISICA"

        detalles = cls._construir_detalles(
            orden=orden, es_persona_fisica=es_persona_fisica
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
            es_persona_fisica=es_persona_fisica,
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
                current_app.config.get("URL_LOGO_ARP")
            ),
        )
