import logging
from decimal import Decimal

import requests
from flask import current_app

from app.cache.tipo_cambio_cache_service import (
    TipoCambioCache,
    TipoCambioCacheService,
)


class CurrencyService:
    BASE_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api"

    logger = logging.getLogger(__name__)

    @staticmethod
    def _cache() -> TipoCambioCacheService:
        return TipoCambioCacheService()

    @staticmethod
    def _get_conversion_margin() -> float:
        return current_app.config.get("MARGEN_CONVERSION", 0)

    @staticmethod
    def convertir(from_currency: str, to_currency: str):

        from_currency = from_currency.strip().upper()
        to_currency = to_currency.strip().upper()

        if to_currency == "MXN":
            cache = CurrencyService._cache()
            cached = cache.obtener(from_currency)

            if cached is not None:
                CurrencyService.logger.debug(
                    "Tipo de cambio %s obtenido desde Redis.",
                    from_currency,
                )
                return cached.valor

        url = (
            f"{CurrencyService.BASE_URL}@latest/v1/currencies/"
            f"{from_currency.lower()}.json"
        )

        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            data = response.json()

            rate = Decimal(str(data[from_currency.lower()][to_currency.lower()]))

            margen = Decimal(str(CurrencyService._get_conversion_margin()))

            rate += margen

            if to_currency == "MXN":
                CurrencyService._cache().guardar(
                    TipoCambioCache(
                        moneda=from_currency,
                        valor=rate,
                    )
                )

            CurrencyService.logger.info(
                "Tipo de cambio %s -> %s = %s (margen: %s)",
                from_currency,
                to_currency,
                rate,
                margen,
            )

            return rate

        except Exception:
            CurrencyService.logger.exception(
                "Error obteniendo conversión %s -> %s",
                from_currency,
                to_currency,
            )
            return None

    @staticmethod
    def calcular_conversion_MXN(
        precio: Decimal,
        from_currency: str,
    ) -> tuple[Decimal, str | None]:

        currency = from_currency.strip().lower()
        
        precio = Decimal(precio)

        if currency == "mxn":
            return precio, None

        try:
            rate = CurrencyService.convertir(currency, "MXN")

            if rate is None:
                mensaje = (
                    f"No fue posible obtener el tipo de cambio "
                    f"de {currency.upper()} a MXN"
                )

                CurrencyService.logger.error(mensaje)
                return precio, mensaje

            return precio * rate, None

        except Exception as e:
            CurrencyService.logger.exception(
                "Error calculando conversión a MXN para moneda %s",
                currency.upper(),
            )

            return precio, f"Error calculando conversión: {e}"
