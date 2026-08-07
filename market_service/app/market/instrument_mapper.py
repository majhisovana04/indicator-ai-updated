# app/market/instrument_mapper.py — updated to cover both exchanges
import requests
import gzip
import json
import io
from datetime import datetime



class InstrumentMapper:
    """
    Loads Upstox's instrument master files for BOTH NSE and BSE,
    building one combined symbol -> instrument_key lookup.
    """

    EXCHANGE_URLS = {
        "NSE": "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
        "BSE": "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz",
    }

    # F&O master — contains stock futures (instrument_type=="FUT", segment=="NSE_FO")
    FO_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

    # Number of days before expiry to roll to the next month's contract
    # (liquidity thins in the final days of the near-month contract)
    FUTURES_ROLLOVER_DAYS = 3

    # ALL_EQUITY_TYPES: everything worth indexing — the mapper should be
    # able to resolve and report on every listed equity, including
    # restricted ones (BE/T2T-equivalent, SME platforms). Filtering those
    # OUT happens separately, via is_freely_tradeable() below, not here —
    # Section 2 of the strategy plan treats hard filters as an explicit
    # pipeline step (so exclusions can be logged/reported), not something
    # baked silently into instrument loading.
    EQUITY_TYPES = {
        "NSE": {"EQ", "BE", "SM", "ST"},
        "BSE": {"A", "B", "T", "X", "XT", "M", "MT", "Z"},
    }

    # TRADEABLE_TYPES: the subset that passes the Section 2 hard filter —
    # freely day-tradeable, not delivery-only/T2T, not an SME-only platform.
    # NSE: BE = trade-to-trade (excluded); SM/ST = SME platform (excluded).
    # BSE: T/X/XT = trade-to-trade or compliance-restricted; Z = shell/
    # watchlist; M/MT = SME platform — all excluded here.
    # VERIFY this split against BSE's current official series list before
    # relying on it in production; series classifications get revised.
    TRADEABLE_TYPES = {
        "NSE": {"EQ"},
        "BSE": {"A", "B"},
    }

    def __init__(self):
        self.symbol_to_key = {}
        self.symbol_to_info = {}
        self.all_equity_symbols = []
        self.scrip_code_to_symbol = {}  # BSE numeric scrip_code -> composite_symbol (e.g. 544467 -> BSE:NSDL)
        self.underlying_to_fut_key = {}  # underlying_symbol -> near-month futures instrument_key
        self._load_all()
        # _load_futures is merged into _load_all for NSE — no second download needed

    def _load_exchange(self, url: str):
        response = requests.get(url)
        response.raise_for_status()
        with gzip.open(io.BytesIO(response.content)) as f:
            return json.load(f)

    def _load_all(self):
        today = datetime.now().date()
        futures_by_underlying: dict[str, list] = {}

        for exchange, url in self.EXCHANGE_URLS.items():
            instruments = self._load_exchange(url)
            valid_types = self.EQUITY_TYPES.get(exchange, set())

            for inst in instruments:
                segment = inst.get("segment", "")

                # ── Equities (NSE_EQ / BSE_EQ) ──
                if segment == f"{exchange}_EQ":
                    if inst.get("instrument_type") not in valid_types:
                        continue
                    symbol = inst.get("trading_symbol")
                    key = inst.get("instrument_key")
                    if symbol and key:
                        composite_symbol = f"{exchange}:{symbol}"
                        self.symbol_to_key[composite_symbol] = key
                        self.symbol_to_info[composite_symbol] = inst
                        self.all_equity_symbols.append(composite_symbol)
                        scrip_code = inst.get("exchange_token")
                        if exchange == "BSE" and scrip_code:
                            self.scrip_code_to_symbol[str(scrip_code)] = composite_symbol

                # ── Futures (NSE_FO only, instrument_type=FUT) — parse in the same pass ──
                elif exchange == "NSE" and segment == "NSE_FO" and inst.get("instrument_type") == "FUT":
                    underlying = inst.get("underlying_symbol")
                    if underlying:
                        futures_by_underlying.setdefault(underlying, []).append(inst)

        # Build underlying -> near-month futures key index from the collected futures
        for underlying, contracts in futures_by_underlying.items():
            contracts.sort(key=lambda x: x.get("expiry", 0))
            for contract in contracts:
                expiry_ts = contract.get("expiry")
                if not expiry_ts:
                    continue
                expiry_date = datetime.fromtimestamp(expiry_ts / 1000).date()
                days_to_expiry = (expiry_date - today).days
                if days_to_expiry >= self.FUTURES_ROLLOVER_DAYS:
                    self.underlying_to_fut_key[underlying] = contract["instrument_key"]
                    break

    def get_instrument_key(self, composite_symbol: str) -> str:
        # Fallback for backwards compatibility: if no exchange is provided, assume NSE
        if ":" not in composite_symbol:
            composite_symbol = f"NSE:{composite_symbol}"

        key = self.symbol_to_key.get(composite_symbol)
        if not key:
            raise ValueError(f"No instrument key found for: {composite_symbol}")
        return key

    def get_futures_key(self, symbol: str) -> str | None:
        """
        Returns the near-month stock futures instrument_key for the given
        underlying stock symbol (e.g. "RELIANCE"), or None if no active
        futures contract exists (cash-only stock, or F&O master unavailable).
        OI signals should degrade to None cleanly when this returns None.
        """
        # Strip exchange prefix if present (e.g. "NSE:RELIANCE" -> "RELIANCE")
        if ":" in symbol:
            symbol = symbol.split(":", 1)[1]
        return self.underlying_to_fut_key.get(symbol)

    def get_instrument_info(self, composite_symbol: str) -> dict:
        """Returns the full raw Upstox dictionary (useful for checking segment/series)."""
        if ":" not in composite_symbol:
            composite_symbol = f"NSE:{composite_symbol}"
        return self.symbol_to_info.get(composite_symbol, {})

    def get_all_equity_symbols(self) -> list[str]:
        return self.all_equity_symbols

    def is_freely_tradeable(self, composite_symbol: str) -> bool:
        """
        Section 2 hard filter check: is this instrument's series freely
        tradeable (not BE/T2T-equivalent, not SME-platform-only)? The
        scoring pipeline should call this BEFORE computing any sub-scores —
        a stock failing this is removed from the candidate pool entirely,
        not down-weighted (per the plan's Section 2: "Applied before any
        scoring — a stock failing these is removed from the candidate pool
        entirely").

        Returns False for unknown symbols (not found in the loaded
        instrument master) as a safe default — an unresolvable symbol
        should not silently pass the filter.
        """
        if ":" not in composite_symbol:
            composite_symbol = f"NSE:{composite_symbol}"
        exchange = composite_symbol.split(":")[0]
        info = self.symbol_to_info.get(composite_symbol)
        if info is None:
            return False
        return info.get("instrument_type") in self.TRADEABLE_TYPES.get(exchange, set())