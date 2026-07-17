import copy
import logging
from decimal import Decimal

from flask import render_template

from app.models.seguimiento import Seguimiento
from app.services.proveedores import BuscadorProducto
from app.services.email_service import EmailService
from app.services.seguimiento_service import SeguimientoService
from app.services.proveedor_service import ProveedorService
from app.services.CurrencyService import CurrencyService

logger = logging.getLogger(__name__)


class SeguimientoMonitorService:
    @classmethod
    def procesar(cls):

        seguimientos = SeguimientoService.obtener_pendientes()

        logger.info(
            "Procesando %s seguimientos.",
            len(seguimientos),
        )

        for seguimiento in seguimientos:
            try:
                cls._procesar_seguimiento(seguimiento)

            except Exception:
                logger.exception(
                    "Error procesando seguimiento %s",
                    seguimiento.id_seguimiento,
                )

    @classmethod
    def _procesar_seguimiento(cls, seguimiento: Seguimiento):

        cambios = []

        orden = seguimiento.orden

        for detalle in orden.detalles:
            resultados, errores = BuscadorProducto.buscar(
                nombre=detalle.producto,
                sku=detalle.clave_producto,
            )

            if errores:
                logger.warning(
                    "Errores consultando '%s': %s",
                    detalle.producto,
                    errores,
                )

            resultados_mxn = cls._convertir_a_mxn(resultados, detalle.producto)

            cambios.extend(
                cls._evaluar_detalle(
                    detalle,
                    resultados_mxn,
                    seguimiento,
                )
            )

        correo_enviado = False

        if cambios:
            html = cls._generar_html(
                orden,
                cambios,
            )

            EmailService.send(
                destinatario=orden.usuario.email,
                asunto=f"Cambios detectados en {orden.clave_orden}",
                html=html,
            )

            correo_enviado = True

        SeguimientoService.registrar_escaneo(
            seguimiento.id_seguimiento,
            correo_enviado=correo_enviado,
        )

    @staticmethod
    def _precio_efectivo(producto):
        descuento = getattr(producto, "descuento", None)

        if descuento is None:
            return producto.precio

        if descuento == 0 or descuento == producto.precio:
            return producto.precio

        return descuento

    @classmethod
    def _convertir_a_mxn(cls, resultados, nombre_producto):
        convertidos = []

        for producto in resultados:
            precio_a_convertir = cls._precio_efectivo(producto)

            precio_mxn, error = CurrencyService.calcular_conversion_MXN(
                precio=precio_a_convertir,
                from_currency=producto.moneda,
            )

            if error:
                logger.warning(
                    "Error convirtiendo precio de '%s' (proveedor %s, moneda %s) a MXN: %s",
                    nombre_producto,
                    producto.proveedor,
                    getattr(producto, "moneda", None),
                    error,
                )
                continue

            producto_mxn = copy.copy(producto)
            producto_mxn.precio = precio_mxn
            convertidos.append(producto_mxn)

        return convertidos

    @classmethod
    def _evaluar_detalle(
        cls,
        detalle,
        resultados,
        seguimiento,
    ):

        if not resultados:
            return []

        productos = {}
        for producto in resultados:
            proveedor = ProveedorService.search_by_nombre(producto.proveedor)
            if proveedor is None:
                proveedor, error = ProveedorService.create(
                    {"nombre": producto.proveedor}
                )
            productos[proveedor.id_proveedor] = producto

        producto_original = productos.get(detalle.proveedor.id_proveedor)

        eventos = []

        if seguimiento.cambio_precio:
            evento = cls._detectar_cambio_precio(
                detalle,
                producto_original,
                Decimal("1.5"),
            )
            if evento:
                eventos.append(evento)

        if seguimiento.sin_stock:
            evento = cls._detectar_sin_stock(
                detalle,
                producto_original,
            )
            if evento:
                eventos.append(evento)

        if seguimiento.mejor_oferta:
            evento = cls._detectar_mejor_oferta(
                detalle,
                resultados,
                seguimiento.diferencia_minima,
            )
            if evento:
                eventos.append(evento)

        return eventos

    @staticmethod
    def _detectar_cambio_precio(
        detalle,
        producto_original,
        margen_cambio_precio=None,
    ):

        if producto_original is None:
            return None

        precio_anterior = Decimal(detalle.precio_unitario)
        precio_actual = Decimal(producto_original.precio)

        if precio_actual == precio_anterior:
            return None

        if margen_cambio_precio and precio_anterior != 0:
            variacion_pct = abs(precio_actual - precio_anterior) / precio_anterior * 100
            if variacion_pct < Decimal(margen_cambio_precio):
                return None

        return {
            "tipo": "precio",
            "producto": detalle.producto,
            "proveedor": detalle.proveedor.nombre,
            "precio_anterior": detalle.precio_unitario,
            "precio_actual": producto_original.precio,
        }

    @staticmethod
    def _detectar_sin_stock(
        detalle,
        producto_original,
    ):
        if producto_original is None:
            logger.info(
                "Sin datos de '%s' para proveedor '%s'; se omite chequeo de stock.",
                detalle.producto,
                detalle.proveedor.nombre,
            )
            return None

        existencia = producto_original.existencia or 0
        cantidad_requerida = detalle.cantidad

        if existencia >= cantidad_requerida:
            return None

        return {
            "tipo": "stock",
            "producto": detalle.producto,
            "proveedor": detalle.proveedor.nombre,
            "existencia_disponible": existencia,
            "cantidad_requerida": cantidad_requerida,
        }

    @staticmethod
    def _detectar_mejor_oferta(
        detalle,
        resultados,
        diferencia_minima,
    ):
        mejor = min(resultados, key=lambda p: Decimal(p.precio))

        if mejor.proveedor == detalle.proveedor.nombre:
            return None

        ahorro = Decimal(detalle.precio_unitario) - Decimal(mejor.precio)

        if ahorro < diferencia_minima:
            return None

        return {
            "tipo": "oferta",
            "producto": detalle.producto,
            "proveedor_actual": detalle.proveedor.nombre,
            "proveedor_nuevo": mejor.proveedor,
            "precio_actual": detalle.precio_unitario,
            "precio_nuevo": mejor.precio,
            "ahorro": ahorro,
        }

    @staticmethod
    def _generar_html(
        orden,
        cambios,
    ):

        return render_template(
            "emails/seguimiento.html",
            orden=orden,
            cambios=cambios,
        )
