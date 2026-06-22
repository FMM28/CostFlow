import logging
import requests
from flask import current_app


class CurrencyService:
    BASE_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api"

    logger = logging.getLogger(__name__)

    @staticmethod
    def _get_conversion_margin():
        return current_app.config.get("MARGEN_CONVERSION", 0)

    @staticmethod
    def convertir(from_currency: str, to_currency: str):

        url = (
            f"{CurrencyService.BASE_URL}@{'latest'}/v1/currencies/"
            f"{from_currency.lower()}.json"
        )

        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            data = response.json()

            rate = data[from_currency.lower()][to_currency.lower()]

            margen = CurrencyService._get_conversion_margin()
            rate += margen

            CurrencyService.logger.info(
                "Tipo de cambio %s -> %s = %s (margen aplicado: %s)",
                from_currency.upper(),
                to_currency.upper(),
                rate,
                margen,
            )

            return rate

        except Exception as e:
            CurrencyService.logger.exception(
                "Error obteniendo conversión %s -> %s",
                from_currency.upper(),
                to_currency.upper(),
            )
            return None

    @staticmethod
    def calcular_conversion_MXN(
        precio: float, from_currency: str
    ) -> tuple[float, str | None]:
        currency = from_currency.strip().lower()

        if currency == "mxn":
            return precio, None

        try:
            rate = CurrencyService.convertir(currency, "mxn")

            if rate is None:
                mensaje = (
                    f"No fue posible obtener el tipo de cambio "
                    f"de {currency.upper()} a MXN"
                )

                CurrencyService.logger.error(mensaje)
                return precio, mensaje

            precio_convertido = precio * rate

            return precio_convertido, None

        except Exception as e:
            CurrencyService.logger.exception(
                "Error calculando conversión a MXN para moneda %s",
                currency.upper(),
            )

            return precio, f"Error calculando conversión: {e}"
