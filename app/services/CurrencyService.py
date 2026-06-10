import requests
from datetime import datetime
from flask import current_app


class CurrencyService:
    BASE_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api"

    @staticmethod
    def _get_latest_date():
        return "latest"

    @staticmethod
    def _get_conversion_margin():
        return current_app.config.get("MARGEN_CONVERSION", 0)

    @staticmethod
    def convertir(from_currency: str, to_currency: str):
        date = CurrencyService._get_latest_date()

        url = f"{CurrencyService.BASE_URL}@{date}/v1/currencies/{from_currency.lower()}.json"

        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            data = response.json()

            rate = data[from_currency.lower()][to_currency.lower()]

            margen = CurrencyService._get_conversion_margin()
            rate += margen

            print(
                f"{from_currency.upper()} → {to_currency.upper()} = {rate} "
                f"(incluye margen: {margen})"
            )

            return rate

        except Exception as e:
            print(f"Error obteniendo conversión: {e}")
            return None