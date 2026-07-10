# app/market/instrument_mapper.py — updated to cover both exchanges
import requests
import gzip
import json
import io


class InstrumentMapper:
    """
    Loads Upstox's instrument master files for BOTH NSE and BSE,
    building one combined symbol -> instrument_key lookup.
    """

    EXCHANGE_URLS = {
        "NSE": "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
        "BSE": "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz",
    }

    def __init__(self):
        self.symbol_to_key = {}
        self.all_equity_symbols = []
        self._load_all()

    def _load_exchange(self, url: str):
        response = requests.get(url)
        response.raise_for_status()
        with gzip.open(io.BytesIO(response.content)) as f:
            return json.load(f)

    def _load_all(self):
        for exchange, url in self.EXCHANGE_URLS.items():
            instruments = self._load_exchange(url)
            for inst in instruments:
                if inst.get("instrument_type") == "EQ":
                    symbol = inst.get("trading_symbol")
                    key = inst.get("instrument_key")
                    if symbol and key:
                        # avoid duplicate symbol collisions across exchanges
                        composite_symbol = f"{exchange}:{symbol}"
                        self.symbol_to_key[composite_symbol] = key
                        self.all_equity_symbols.append(composite_symbol)

    def get_instrument_key(self, composite_symbol: str) -> str:
        # Fallback for backwards compatibility: if no exchange is provided, assume NSE
        if ":" not in composite_symbol:
            composite_symbol = f"NSE:{composite_symbol}"
            
        key = self.symbol_to_key.get(composite_symbol)
        if not key:
            raise ValueError(f"No instrument key found for: {composite_symbol}")
        return key

    def get_all_equity_symbols(self) -> list[str]:
        return self.all_equity_symbols