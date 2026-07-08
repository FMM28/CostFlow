from app.services.pdf.generators.normal_generator import NormalGenerator
from app.services.pdf.generators.unam_generator import UNAMGenerator
from app.services.pdf.cotizacion_mapper import CotizacionMapper
from app.models.orden import Orden


class CotizacionPDFService:
    @staticmethod
    def generar(orden: Orden) -> bytes:

        cotizacion = CotizacionMapper.from_orden(orden=orden)

        if cotizacion.es_unam:
            generator = UNAMGenerator()
        else:
            generator = NormalGenerator()

        return generator.generar(cotizacion)
