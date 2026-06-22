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


class ImportacionDigitalService:
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
        texto = texto.strip()

        return texto

    @staticmethod
    def _mapear_columnas(df: pd.DataFrame) -> pd.DataFrame:
        """
        Mapea los nombres de columnas a un formato estándar.
        """

        mapeo_columnas = {
            "nº": "numero_interno",
            "sku": "sku",
            "descripción": "descripcion",
            "descripcion": "descripcion",
            "condición": "condicion",
            "condicion": "condicion",
            "periodo de garantía": "periodo_garantia",
            "periodo de garantia": "periodo_garantia",
            "cód. categoría producto": "cod_categoria",
            "cod categoria producto": "cod_categoria",
            "cód. fabricante": "cod_fabricante",
            "cod fabricante": "cod_fabricante",
            "inventario": "inventario",
            "precio distribuidor": "precio_distribuidor",
            "precio oferta usd": "precio_oferta",
        }

        rename_dict = {}

        for columna in df.columns:
            columna_str = str(columna).strip()
            columna_norm = ImportacionDigitalService._normalizar_texto(columna_str)

            for clave_original, clave_nueva in mapeo_columnas.items():
                clave_norm = ImportacionDigitalService._normalizar_texto(clave_original)

                if columna_norm == clave_norm:
                    rename_dict[columna] = clave_nueva
                    break

        logger.info(f"Columnas mapeadas: {rename_dict}")

        return df.rename(columns=rename_dict)

    @staticmethod
    def subir_excel(ruta_excel: str):

        logger.info(f"Iniciando importación desde: {ruta_excel}")

        NOMBRE_PROVEEDOR = "Importacion Digital"

        proveedor = ProveedorService.search_by_nombre(NOMBRE_PROVEEDOR)

        error = None

        if not proveedor:
            logger.info("Proveedor no encontrado, creando nuevo...")

            proveedor, error = ProveedorService.create({"nombre": NOMBRE_PROVEEDOR})

            if error:
                logger.error(f"Error al crear proveedor: {error}")
                return 0

        logger.info(f"Proveedor ID: {proveedor.id_proveedor}")

        try:
            df = pd.read_excel(ruta_excel, header=7)

            df = df.iloc[:-3]

            df = ImportacionDigitalService._mapear_columnas(df)

            columnas_necesarias = ["sku", "descripcion", "precio_distribuidor"]

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
                sku = str(row.get("sku", "")).strip()

                if not sku or sku == "nan":
                    omitidos += 1
                    continue

                precio = row.get("precio_distribuidor")

                if pd.isna(precio):
                    omitidos += 1
                    continue

                precio = Decimal(str(precio))

                precio_oferta = row.get("precio_oferta")

                descripcion = str(row.get("descripcion", "")).strip()

                existencia = row.get("inventario")
                existencia = int(existencia) if not pd.isna(existencia) else 0

                clave_interna = row.get("numero_interno")
                clave_interna = (
                    str(clave_interna).strip()
                    if clave_interna is not None and not pd.isna(clave_interna)
                    else None
                )

                producto = Producto(
                    id_proveedor=proveedor.id_proveedor,
                    descripcion=descripcion,
                    clave_producto=sku,
                    precio=precio,
                    descuento=precio_oferta if precio_oferta != 0.0 else None,
                    moneda="USD",
                    existencia=existencia,
                    clave_interna=clave_interna,
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
