# app/market/upstox_quote_client.py
import os
from dotenv import load_dotenv
load_dotenv()

import requests
from market_service.app.market.instrument_mapper import InstrumentMapper


class UpstoxQuoteClient:
    """
    Fetches CURRENT/TODAY'S market quote (live price, today's OHLC,
    volume) for one or more instruments in a single call.
    Does NOT provide historical data — see UpstoxClient for that.
    """

    BASE_URL = "https://api.upstox.com/v2/market-quote/quotes"

    def __init__(self):
        self.access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("UPSTOX_ACCESS_TOKEN not found in environment")
        self.mapper = InstrumentMapper()

    def fetch_quotes(self, symbols: list[str]) -> dict:
        instrument_keys = [self.mapper.get_instrument_key(s) for s in symbols]
        keys_param = ",".join(instrument_keys)

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        params = {"instrument_key": keys_param}

        response = requests.get(self.BASE_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "success":
            raise ValueError(f"Upstox quote fetch failed: {data}")

        return data["data"]

    def fetch_quote_by_key(self, instrument_key: str) -> dict:
        """
        Fetches a quote using a raw instrument_key directly, bypassing
        the symbol->key mapper. Needed for instruments like India VIX
        that aren't part of the Nifty equity universe the mapper knows about.
        """
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        params = {"instrument_key": instrument_key}

        response = requests.get(self.BASE_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "success":
            raise ValueError(f"Upstox quote fetch failed: {data}")

        quote_data = data["data"]
        if not quote_data:
            raise ValueError(f"No quote data returned for {instrument_key}")

        return next(iter(quote_data.values()))