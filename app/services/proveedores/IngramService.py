import csv
import io
import logging
import zipfile
from datetime import datetime
from decimal import Decimal, InvalidOperation

import paramiko

from app import db
from app.models.producto import Producto
from app.services.proveedor_credenciales_service import ProveedorCredencialesService
from app.services.proveedor_service import ProveedorService


logger = logging.getLogger(__name__)


class IngramService:
    PROVEEDOR = "INGRAM"
    ARCHIVO_ZIP = "PRICE.ZIP"
    ARCHIVO_TXT = "PRICE.TXT"

    @classmethod
    def actualizar_inventario(cls):
        """
        Descarga PRICE.ZIP desde el SFTP de Ingram, extrae PRICE.TXT e importa
        los productos a la base de datos.
        """

        proveedor = ProveedorService.search_by_nombre(cls.PROVEEDOR)

        if not proveedor:
            proveedor, error = ProveedorService.create({"nombre": cls.PROVEEDOR})

            if error:
                logger.error(error)
                return 0

        credenciales = ProveedorCredencialesService.obtener(cls.PROVEEDOR)

        if credenciales is None:
            logger.error(
                "No existen credenciales configuradas para %s",
                cls.PROVEEDOR,
            )
            return 0

        host = credenciales.get("host")
        port = credenciales.get("port")
        username = credenciales.get("username")
        password = credenciales.get("password")

        if not all([host, port, username, password]):
            logger.error(
                "Las credenciales de %s están incompletas",
                cls.PROVEEDOR,
            )
            return 0

        transport = None
        sftp = None

        try:
            logger.info("Conectando al SFTP de Ingram...")

            transport = paramiko.Transport((host, int(port)))
            transport.connect(
                username=username,
                password=password,
            )

            sftp = paramiko.SFTPClient.from_transport(transport)

            logger.info("Descargando %s...", cls.ARCHIVO_ZIP)

            with io.BytesIO() as zip_buffer:
                sftp.getfo(cls.ARCHIVO_ZIP, zip_buffer)
                zip_buffer.seek(0)

                with zipfile.ZipFile(zip_buffer) as zf:
                    with zf.open(cls.ARCHIVO_TXT) as txt_file:
                        cls._procesar_archivo(
                            txt_file,
                            proveedor.id_proveedor,
                        )

            logger.info("Importación de Ingram finalizada.")

        finally:
            if sftp:
                sftp.close()

            if transport:
                transport.close()

    @classmethod
    def _procesar_archivo(cls, archivo, id_proveedor):
        columnas = [
            "Action Indicator",
            "Ingram Part Number",
            "Vendor Number",
            "Vendor Name",
            "Part Description Line 1",
            "Part Description Line 2",
            "Price-retail",
            "Vendor Part Number",
            "Peso",
            "UPC-CODE",
            "Largo",
            "Ancho",
            "Alto",
            "Cust-cost-c",
            "Cust-cost",
            "Product Key",
            "Stock Flag",
            "Price Status",
            "Alliance",
            "CPU Code",
            "New Media",
            "Category-Sub Cat",
            "WHSE-HAS-STOCK-SW",
            "Rebate to cost",
            "Subtitute Part",
            "Quantity avail",
        ]

        lector = csv.reader(
            io.TextIOWrapper(
                archivo,
                encoding="latin-1",
                newline="",
            ),
            delimiter=",",
            quotechar='"',
        )

        try:
            Producto.query.filter_by(id_proveedor=id_proveedor).delete(
                synchronize_session=False
            )

            productos = []
            ahora = datetime.now()

            for fila in lector:
                if not fila:
                    continue

                if len(fila) < len(columnas):
                    fila.extend([""] * (len(columnas) - len(fila)))
                elif len(fila) > len(columnas):
                    fila = fila[: len(columnas)]

                datos = dict(zip(columnas, fila))

                descripcion = (
                    f"{datos['Part Description Line 1'].strip()} "
                    f"{datos['Part Description Line 2'].strip()}"
                ).strip()

                productos.append(
                    Producto(
                        id_proveedor=id_proveedor,
                        descripcion=descripcion[:255],
                        clave_producto=datos["Vendor Part Number"].strip(),
                        precio=cls._decimal(datos["Cust-cost"]),
                        descuento=Decimal("0.00"),
                        moneda="MXN",
                        existencia=cls._entero(datos["Quantity avail"]),
                        clave_interna=datos["Ingram Part Number"].strip(),
                        actualizado_en=ahora,
                    )
                )

                if len(productos) >= 1000:
                    db.session.bulk_save_objects(productos)
                    db.session.flush()
                    productos.clear()

            if productos:
                db.session.bulk_save_objects(productos)

            db.session.commit()

        except Exception:
            db.session.rollback()
            logger.exception(
                "Error al procesar PRICE.TXT de Ingram, se revirtieron los cambios."
            )
            raise

    @staticmethod
    def _decimal(valor):
        if valor is None:
            return Decimal("0.00")

        valor = str(valor).replace("$", "").replace(",", "").strip()

        if not valor:
            return Decimal("0.00")

        try:
            return Decimal(valor)
        except InvalidOperation:
            return Decimal("0.00")

    @staticmethod
    def _entero(valor):
        if valor is None:
            return 0

        valor = str(valor).replace(",", "").strip()

        if not valor:
            return 0

        try:
            return int(float(valor))
        except ValueError:
            return 0
