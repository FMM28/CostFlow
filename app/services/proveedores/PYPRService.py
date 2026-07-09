import re
import unicodedata
from decimal import Decimal
from datetime import datetime
import logging

import pandas as pd

from app import db
from app.models.producto import Producto
from app.services.proveedor_service import ProveedorService

logger = logging.getLogger(__name__)


class PYPRService:
    @staticmethod
    def _normalizar_texto(texto: str) -> str:
        """
        Normaliza texto eliminando acentos, caracteres especiales y espacios extra.
        """
        if not isinstance(texto, str):
            return str(texto) if texto else ""

        texto = texto.lower()

        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))

        texto = re.sub(r"[^a-z0-9\s]", " ", texto)
        texto = re.sub(r"\s+", " ", texto)

        return texto.strip()

    @staticmethod
    def _mapear_columnas(df: pd.DataFrame) -> pd.DataFrame:
        """
        Mapea los nombres de columnas a un formato estándar.
        """

        mapeo_columnas = {
            "articulo": "articulo",
            "descripción": "descripcion",
            "clave fabricante pyp": "clave_fabricante",
            "fabricante": "fabricante",
            "categoría": "categoria",
            "precio especial": "precio",
            "promo": "promo",
            "disponible": "existencia",
        }

        rename_dict = {}

        for columna in df.columns:
            columna_str = str(columna).strip()
            columna_norm = PYPRService._normalizar_texto(columna_str)

            for original, nuevo in mapeo_columnas.items():
                if columna_norm == PYPRService._normalizar_texto(original):
                    rename_dict[columna] = nuevo
                    break

        return df.rename(columns=rename_dict)

    @staticmethod
    def _parse_decimal(valor):
        if pd.isna(valor):
            return None

        valor = str(valor).strip()

        valor = valor.replace("$", "").replace(",", "").strip()

        if not valor or valor == "-":
            return None

        return Decimal(valor)

    @staticmethod
    def subir_excel(ruta_excel: str):

        logger.info(f"Iniciando importación desde: {ruta_excel}")

        NOMBRE_PROVEEDOR = "PYPR"

        proveedor = ProveedorService.search_by_nombre(NOMBRE_PROVEEDOR)

        if not proveedor:
            logger.info("Proveedor no encontrado, creando nuevo...")

            proveedor, error = ProveedorService.create({"nombre": NOMBRE_PROVEEDOR})

            if error:
                logger.error(f"Error al crear proveedor: {error}")
                return 0

        logger.info(f"Proveedor ID: {proveedor.id_proveedor}")

        try:
            # Encabezados en la segunda fila
            df = pd.read_excel(ruta_excel, header=1)

            df = PYPRService._mapear_columnas(df)

            columnas_necesarias = [
                "articulo",
                "descripcion",
                "clave_fabricante",
                "precio",
            ]

            faltantes = [c for c in columnas_necesarias if c not in df.columns]

            if faltantes:
                raise ValueError(f"Faltan columnas necesarias: {faltantes}")

        except Exception as e:
            logger.error(f"Error leyendo Excel: {e}")
            raise

        Producto.query.filter_by(id_proveedor=proveedor.id_proveedor).delete()

        productos = []
        omitidos = 0

        for index, row in df.iterrows():
            try:
                clave_producto = str(row.get("clave_fabricante", "")).strip()

                if not clave_producto or clave_producto.lower() == "nan":
                    omitidos += 1
                    continue

                precio = PYPRService._parse_decimal(row.get("precio"))

                if precio is None:
                    omitidos += 1
                    continue

                descuento = PYPRService._parse_decimal(row.get("promo"))

                descripcion = str(row.get("descripcion", "")).strip()

                existencia = row.get("existencia")
                existencia = int(existencia) if not pd.isna(existencia) else 0

                clave_interna = row.get("articulo")
                clave_interna = (
                    str(clave_interna).strip()
                    if clave_interna is not None and not pd.isna(clave_interna)
                    else None
                )

                producto = Producto(
                    id_proveedor=proveedor.id_proveedor,
                    descripcion=descripcion,
                    clave_producto=clave_producto,
                    clave_interna=clave_interna,
                    precio=precio,
                    descuento=descuento,
                    moneda="USD",
                    existencia=existencia,
                    actualizado_en=datetime.now(),
                )

                productos.append(producto)

            except Exception as e:
                logger.error(f"Error fila {index}: {e}")
                omitidos += 1
                continue

        try:
            db.session.bulk_save_objects(productos)
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error guardando en BD: {e}")
            raise

        logger.info(f"Importados: {len(productos)}, omitidos: {omitidos}")

        return len(productos)
