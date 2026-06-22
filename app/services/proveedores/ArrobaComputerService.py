import re
import unicodedata
from decimal import Decimal
from datetime import datetime
import logging

import pandas as pd

from app import db
from app.models.producto import Producto
from app.models.existencia_producto import ExistenciaProducto
from app.services.proveedor_service import ProveedorService

logger = logging.getLogger(__name__)


class ArrobaComputerService:
    @staticmethod
    def _normalizar_texto(texto: str) -> str:

        if not isinstance(texto, str):
            return str(texto) if texto else ""

        texto = texto.lower()

        texto = unicodedata.normalize("NFKD", texto)

        texto = "".join(c for c in texto if not unicodedata.combining(c))

        texto = re.sub(r"[^a-z0-9\s]", " ", texto)

        texto = re.sub(r"\s+", " ", texto)

        return texto.strip()

    @staticmethod
    def _mapear_columnas(df: pd.DataFrame):

        mapeo_columnas = {
            "upc ean": "upc",
            "articulo": "articulo",
            "descripcion": "descripcion",
            "departamento": "departamento",
            "marca": "marca",
            "total": "total",
            "ave": "AVE",
            "cen": "CEN",
            "gdl": "GDL",
            "moneda": "moneda",
            "precio": "precio",
            "descuento": "descuento",
            "promocion": "promocion",
            "precio en pesos": "precio_pesos",
        }

        rename_dict = {}

        for columna in df.columns:
            columna_norm = ArrobaComputerService._normalizar_texto(str(columna).strip())

            for original, nuevo in mapeo_columnas.items():
                original_norm = ArrobaComputerService._normalizar_texto(original)

                if columna_norm == original_norm:
                    rename_dict[columna] = nuevo

                    break

        logger.info(f"Columnas mapeadas: {rename_dict}")

        return df.rename(columns=rename_dict)

    @staticmethod
    def subir_excel(ruta_excel):

        logger.info(f"Iniciando importación {ruta_excel}")

        NOMBRE_PROVEEDOR = "ARROBA COMPUTER"

        proveedor = ProveedorService.search_by_nombre(NOMBRE_PROVEEDOR)

        if not proveedor:
            proveedor, error = ProveedorService.create({"nombre": NOMBRE_PROVEEDOR})

            if error:
                logger.error(error)

                return 0

        try:
            tipo_cambio_df = pd.read_excel(
                ruta_excel, sheet_name="LP Almacen General", header=None, nrows=1
            )

            valor_tc = str(tipo_cambio_df.iloc[0, 3])

            valor_tc = valor_tc.replace("$", "").replace(",", ".").strip()

            tipo_cambio = Decimal(valor_tc)

            logger.info(f"Tipo de cambio: {tipo_cambio}")

            df = pd.read_excel(ruta_excel, sheet_name="LP Almacen General", header=3)

            df = ArrobaComputerService._mapear_columnas(df)

            columnas_necesarias = [
                "articulo",
                "descripcion",
                "precio",
                "moneda",
            ]

            faltantes = [c for c in columnas_necesarias if c not in df.columns]

            if faltantes:
                raise ValueError(f"Faltan columnas: {faltantes}")

        except Exception as e:
            logger.error(e)

            raise

        try:
            productos_a_eliminar = Producto.query.filter_by(
                id_proveedor=proveedor.id_proveedor
            ).all()

            ids_productos = [p.id_producto for p in productos_a_eliminar]

            if ids_productos:
                existencias_eliminadas = ExistenciaProducto.query.filter(
                    ExistenciaProducto.id_producto.in_(ids_productos)
                ).delete(synchronize_session=False)
                logger.info(f"Existencias eliminadas: {existencias_eliminadas}")

                productos_eliminados = Producto.query.filter_by(
                    id_proveedor=proveedor.id_proveedor
                ).delete()
                logger.info(f"Productos eliminados: {productos_eliminados}")

                db.session.commit()
                logger.info("Registros antiguos eliminados correctamente")
            else:
                logger.info("No hay productos existentes para eliminar")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al eliminar registros antiguos: {e}")
            raise

        productos_importados = 0
        omitidos = 0

        for index, row in df.iterrows():
            try:
                sku = str(row.get("articulo", "")).strip()

                if not sku:
                    omitidos += 1
                    logger.warning(f"Fila {index}: SKU vacío, omitiendo")
                    continue

                descripcion = str(row.get("descripcion", "")).strip()

                precio = row.get("precio")

                if pd.isna(precio):
                    omitidos += 1
                    logger.warning(f"Fila {index}: Precio vacío, omitiendo SKU: {sku}")
                    continue

                precio = Decimal(str(precio))

                moneda_original = str(row.get("moneda", "")).strip()

                moneda_normalizada = ArrobaComputerService._normalizar_texto(
                    moneda_original
                )

                es_dolar = moneda_normalizada in {"dolar", "dolares", "usd"}

                if es_dolar:
                    precio *= tipo_cambio
                    moneda_guardada = "MXN"

                elif moneda_normalizada in {"peso", "pesos", "mxn"}:
                    moneda_guardada = "MXN"

                else:
                    logger.warning(f"Moneda desconocida: {moneda_original}")

                    moneda_guardada = (
                        moneda_original.upper()[:3] if moneda_original else "N/A"
                    )

                promocion = ArrobaComputerService._normalizar_texto(
                    str(row.get("promocion", ""))
                )

                if promocion == "si":
                    descuento = Decimal(row.get("descuento"))

                    if pd.notna(descuento):
                        if es_dolar:
                            descuento *= tipo_cambio

                        descuento = Decimal(str(descuento))
                    else:
                        descuento = None

                else:
                    descuento = None

                existencia_total = row.get("total")

                existencia_total = (
                    int(existencia_total) if pd.notna(existencia_total) else 0
                )

                upc = row.get("upc")

                upc = str(upc).strip() if pd.notna(upc) else None

                producto = Producto(
                    id_proveedor=proveedor.id_proveedor,
                    descripcion=descripcion,
                    clave_producto=sku,
                    precio=precio.quantize(Decimal("0.01")),
                    descuento=descuento,
                    moneda=moneda_guardada,
                    existencia=existencia_total,
                    clave_interna=upc,
                    actualizado_en=datetime.now(),
                )

                db.session.add(producto)

                db.session.flush()

                for sucursal in ["AVE", "CEN", "GDL"]:
                    if sucursal in df.columns:
                        existencia = row.get(sucursal)

                        if pd.isna(existencia):
                            continue

                        db.session.add(
                            ExistenciaProducto(
                                id_producto=producto.id_producto,
                                sucursal=sucursal,
                                existencia=int(existencia),
                            )
                        )
                    else:
                        logger.warning(
                            f"Columna {sucursal} no encontrada en el archivo"
                        )

                productos_importados += 1

            except Exception as e:
                logger.error(f"Error en fila {index}: {e}")
                omitidos += 1
                continue

        try:
            db.session.commit()
            logger.info("Importación completada exitosamente")
            logger.info(f"Importados: {productos_importados}")
            logger.info(f"Omitidos: {omitidos}")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al guardar en base de datos: {e}")
            raise

        return productos_importados
