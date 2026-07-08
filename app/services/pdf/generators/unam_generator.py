from app.services.pdf.generators.base_generator import BaseGenerator


class UNAMGenerator(BaseGenerator):

    def extra_context(self, cotizacion):

        return {
            "es_unam": True,
        }