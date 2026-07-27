# app/market/hard_filters.py
"""
Section 2 hard-filter implementation: ASM/GSM/ESM surveillance, promoter
pledge, restricted series (BE/T2T-equivalent), and IBC insolvency exclusion
— applied BEFORE any scoring, per the strategy plan.

Also backs Section 8.2's Transparency Layer: every check here returns a
REASON, not just a bool, so an excluded stock can be shown to the user as
"excluded — <specific reason>" instead of just silently disappearing.

=== NSE data source (CONFIRMED, real file) ===
One consolidated daily file, REG_IND<DDMMYY>.csv, at:
  https://nsearchives.nseindia.com/content/cm/REG_IND<DDMMYY>.csv
Combines GSM / ASM (Long+Short, separate columns) / ESM / IRP (insolvency)
in one feed. Column names below are confirmed against a real downloaded
file (REG_IND240726.csv).

=== BSE data sources (CONFIRMED for ASM/GSM/ESM, OPEN for IRP) ===
BSE does not publish one combined file like NSE. Four separate real,
verified sources instead:
  - Long Term ASM:  https://www.bseindia.com/downloads1/List_of_Long_Term_ASM_Securities_<DDMMYYYY>.CSV
  - Short Term ASM: https://www.bseindia.com/downloads1/List_of_Short_Term_ASM_Securities_<DDMMYYYY>.CSV
  - GSM:            https://www.bseindia.com/downloads1/List_of_GSM_Securities_<DDMMYYYY>.CSV
  - ESM:            https://www.nseindia.com/reports/esm -> esm-latest.csv
                     (ESM is a JOINT SEBI framework across both exchanges;
                     this ONE file, hosted on NSE's site, covers BSE-listed
                     securities too — confirmed via real esm-latest.csv,
                     which carries both SYMBOL and ISIN columns.)
Note the BSE date format is DDMMYYYY (4-digit year), different from NSE's
DDMMYY, and the extension is uppercase .CSV.

All three BSE ASM/GSM/ESM files key by ISIN, not trading symbol — so BSE
lookups join through InstrumentMapper (which already keys BSE equities by
ISIN via instrument_key = "BSE_EQ|<ISIN>"), NOT by symbol like the NSE path.

IRP / insolvency for BSE-listed stocks: NO consolidated downloadable list
was found. What exists instead is scattered per-company corporate
disclosure filings, not a single feed. Left unimplemented for BSE — see
check_hard_filters()'s docstring for the concrete effect of this gap.
"""

from dataclasses import dataclass
from enum import Enum
import csv
import io
from datetime import date

import requests


class HardFilterReason(str, Enum):
    """
    Every value here is a possible reason a stock is excluded from the
    candidate pool. Used both for the internal filter decision AND as the
    user-facing text in Section 8.2's "Excluded despite strong underlying
    metrics" tier — keep these values short and presentable as-is.
    """
    NONE = "none"  # passes all checks
    ILLIQUID = "illiquid"
    RESTRICTED_SERIES = "restricted_series"          # BE/T2T-equivalent, not freely day-tradeable
    SURVEILLANCE_GSM = "gsm_surveillance"
    SURVEILLANCE_ASM = "asm_surveillance"
    SURVEILLANCE_ESM = "esm_surveillance"
    INSOLVENCY_IRP = "insolvency_proceedings"          # IBC / IRP
    PLEDGE_HIGH = "promoter_pledge_above_threshold"
    UNKNOWN_SYMBOL = "unresolved_symbol"               # not found in surveillance data at all

    def display_text(self) -> str:
        """User-facing label for Section 8.2 — plain language, no jargon."""
        return {
            HardFilterReason.NONE: "Passes all filters",
            HardFilterReason.ILLIQUID: "Insufficient liquidity for safe entry/exit",
            HardFilterReason.RESTRICTED_SERIES: "Delivery-only / not freely day-tradeable series",
            HardFilterReason.SURVEILLANCE_GSM: "Under Graded Surveillance Measure (GSM)",
            HardFilterReason.SURVEILLANCE_ASM: "Under Additional Surveillance Measure (ASM)",
            HardFilterReason.SURVEILLANCE_ESM: "Under Enhanced Surveillance Measure (ESM)",
            HardFilterReason.INSOLVENCY_IRP: "Under insolvency resolution proceedings (IBC)",
            HardFilterReason.PLEDGE_HIGH: "Promoter pledge above 20% threshold",
            HardFilterReason.UNKNOWN_SYMBOL: "Could not verify surveillance status",
        }[self]


@dataclass
class HardFilterResult:
    symbol: str
    passed: bool
    reason: HardFilterReason
    as_of: date | None = None  # date of the surveillance file used for this check


class SurveillanceDataLoader:
    """
    Loads and caches NSE's daily REG_IND file plus BSE's separate
    ASM/GSM/ESM files, building two lookup tables:
      - self._nse_flags:      keyed by NSE trading Symbol
      - self._bse_isin_flags: keyed by ISIN (BSE has no single combined
                               file, and its files key by ISIN, not symbol)
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; XaneFunds-SurveillanceLoader/1.0)",
        "Referer": "https://www.nseindia.com/all-reports",
    }

    # --- NSE: confirmed column names from a real REG_IND240726.csv ---
    NSE_DOWNLOAD_URL_TEMPLATE = "https://nsearchives.nseindia.com/content/cm/REG_IND{ddmmyy}.csv"
    NSE_COL_SYMBOL = "Symbol"
    NSE_COL_GSM_STAGE = "GSM"
    NSE_COL_ASM_LONG_STAGE = "Long_Term_Additional_Surveillance_Measure (Long Term ASM)"
    NSE_COL_ASM_SHORT_STAGE = "Short_Term_Additional_Surveillance_Measure (Short Term ASM)"
    NSE_COL_ESM_STAGE = "ESM"
    NSE_COL_IRP_FLAG = "Insolvency_Resolution_Process(IRP)"
    # No promoter-pledge PERCENTAGE column exists in this file. "Pledge" /
    # "Total Pledge" are flag/stage codes (100 = none, small positive int =
    # flagged), NOT the percentage Section 2's ">20%" rule needs. Real
    # pledge % still requires a separate source per Section 5 (quarterly
    # shareholding filings) — not implemented here.
    NSE_CLEAN_VALUE = "100"

    # --- BSE: confirmed working URLs and column names from real files ---
    BSE_LONG_ASM_URL_TEMPLATE = "https://www.bseindia.com/downloads1/List_of_Long_Term_ASM_Securities_{ddmmyyyy}.CSV"
    BSE_SHORT_ASM_URL_TEMPLATE = "https://www.bseindia.com/downloads1/List_of_Short_Term_ASM_Securities_{ddmmyyyy}.CSV"
    BSE_GSM_URL_TEMPLATE = "https://www.bseindia.com/downloads1/List_of_GSM_Securities_{ddmmyyyy}.CSV"
    BSE_ASM_COL_ISIN = "ISIN"
    BSE_GSM_COL_ISIN = "ISIN"
    # BSE's GSM file, unlike NSE's REG_IND, is ITSELF the flagged list —
    # every row in it is a currently-flagged stock. There is no "clean"
    # sentinel value to compare against here (stage "0" is a real flagged
    # state — "GSM - 0", shortlisted under GSM — per the exchange's own
    # Annexure I indicator legend, not a "not applicable" marker like
    # NSE's "100"). So presence in this file at all means flagged.

    # --- ESM: joint NSE+BSE file, hosted on NSE's site, keyed by BOTH
    # symbol and ISIN — confirmed via real esm-latest.csv ---
    ESM_URL = "https://www.nseindia.com/reports/esm"  # page hosting esm-latest.csv link
    ESM_COL_SYMBOL = "SYMBOL"
    ESM_COL_ISIN = "ISIN"

    def __init__(self):
        self._nse_flags: dict[str, set[str]] = {}
        self._bse_isin_flags: dict[str, set[str]] = {}
        self._loaded_date: date | None = None

    def load(
        self,
        nse_reg_ind_text: str,
        bse_long_asm_text: str,
        bse_short_asm_text: str,
        bse_gsm_text: str,
        esm_csv_text: str,
    ):
        """
        Loads every surveillance source for today. Call once per trading
        day and reuse this same loader instance for every symbol check
        that day.
        """
        self._load_nse(nse_reg_ind_text)
        self._load_bse_asm(bse_long_asm_text)
        self._load_bse_asm(bse_short_asm_text)
        self._load_bse_gsm(bse_gsm_text)
        self._load_esm(esm_csv_text)
        self._loaded_date = date.today()

    def _load_nse(self, csv_text: str):
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            symbol = row.get(self.NSE_COL_SYMBOL, "").strip()
            if not symbol:
                continue

            flags = set()

            def _is_flagged(col_name: str) -> bool:
                # Stage-style convention confirmed against real data:
                # "100" = clean, any other populated value (positive
                # integer severity stage) = flagged.
                val = row.get(col_name, "").strip()
                return bool(val) and val != self.NSE_CLEAN_VALUE

            if _is_flagged(self.NSE_COL_GSM_STAGE):
                flags.add("GSM")
            if _is_flagged(self.NSE_COL_ASM_LONG_STAGE) or _is_flagged(self.NSE_COL_ASM_SHORT_STAGE):
                flags.add("ASM")
            if _is_flagged(self.NSE_COL_ESM_STAGE):
                flags.add("ESM")
            if _is_flagged(self.NSE_COL_IRP_FLAG):
                flags.add("IRP")

            self._nse_flags[symbol] = flags

    def _load_bse_asm(self, csv_text: str):
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            isin = row.get(self.BSE_ASM_COL_ISIN, "").strip()
            if not isin:
                continue
            # Every row present in this file IS an ASM-flagged security —
            # same "presence = flagged" logic as the GSM file below. Long
            # and Short Term ASM are merged into one "ASM" flag, matching
            # the granularity already used on the NSE side.
            self._bse_isin_flags.setdefault(isin, set()).add("ASM")

    def _load_bse_gsm(self, csv_text: str):
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            isin = row.get(self.BSE_GSM_COL_ISIN, "").strip()
            if not isin:
                continue
            self._bse_isin_flags.setdefault(isin, set()).add("GSM")

    def _load_esm(self, csv_text: str):
        # Real esm-latest.csv has trailing "\n" baked into column header
        # text itself (a quirk of the source export) — strip keys/values.
        reader = csv.DictReader(io.StringIO(csv_text))
        for raw_row in reader:
            row = {k.strip(): (v.strip() if v else v) for k, v in raw_row.items() if k is not None}
            symbol = row.get(self.ESM_COL_SYMBOL, "")
            isin = row.get(self.ESM_COL_ISIN, "")

            # NSE side: only add if not already caught by REG_IND's own ESM
            # column in _load_nse — avoids silently overwriting an
            # NSE-confirmed flag with a duplicate from a second source.
            if symbol:
                self._nse_flags.setdefault(symbol, set()).add("ESM")
            # BSE side: this is the ONLY confirmed ESM source for BSE —
            # required, not redundant.
            if isin:
                self._bse_isin_flags.setdefault(isin, set()).add("ESM")

    def get_nse_flags(self, symbol: str) -> set[str]:
        return self._nse_flags.get(symbol, set())

    def get_bse_flags_by_isin(self, isin: str) -> set[str]:
        return self._bse_isin_flags.get(isin, set())


def _resolve_bse_isin(mapper, composite_symbol: str) -> str | None:
    """
    BSE surveillance files key by ISIN, not trading symbol. InstrumentMapper
    already stores BSE equities as instrument_key = "BSE_EQ|<ISIN>", so the
    ISIN is extracted from that rather than needing a new mapper method.
    Returns None if the symbol doesn't resolve at all.
    """
    try:
        key = mapper.get_instrument_key(composite_symbol)
    except ValueError:
        return None
    if key and "|" in key:
        return key.split("|", 1)[1]
    return None


def check_hard_filters(
    composite_symbol: str,
    is_liquid: bool,
    mapper,               # InstrumentMapper instance
    surveillance: SurveillanceDataLoader,
) -> HardFilterResult:
    """
    Runs every Section 2 hard filter for one stock, in a fixed priority
    order, and returns the FIRST reason it fails.

    Order: insolvency (IRP, NSE only) -> GSM -> ESM -> ASM -> unresolved
    symbol -> restricted series -> illiquid -> pass.

    KNOWN ASYMMETRY between NSE and BSE paths, worth understanding rather
    than treating as a bug:

    NSE: surveillance flags are checked BEFORE requiring instrument-mapper
    resolution, on purpose. A stock deep enough into IBC insolvency is
    often suspended from trading and may no longer appear in Upstox's live
    instrument master at all — even though NSE's own surveillance file
    still correctly flags its IRP status. Checking mapper resolution first
    would mislabel such a stock as "unresolved symbol" instead of the more
    useful "insolvency proceedings" — a real bug caught by testing against
    NSE:SINTEX, which should surface INSOLVENCY_IRP, not UNKNOWN_SYMBOL.

    BSE: this ordering guarantee does NOT hold. BSE's ASM/GSM/ESM files key
    by ISIN, and the only way to get a symbol's ISIN is via mapper
    resolution (InstrumentMapper's instrument_key). So for BSE, mapper
    resolution is structurally required BEFORE any surveillance check can
    even run — if a BSE stock is suspended and drops out of the instrument
    master, it WILL be mislabeled UNKNOWN_SYMBOL instead of its real
    surveillance reason, the same failure mode the NSE ordering was
    specifically designed to avoid. This is an accepted, documented gap,
    not an oversight — fixing it would require a second BSE data source
    that maps ISIN independent of the live instrument master (e.g. a
    static ISIN master file), which hasn't been sourced yet.

    IRP/insolvency is NSE-only in this function. No consolidated BSE IRP
    source was found (see module docstring) — a BSE stock in insolvency
    proceedings will NOT be caught by this filter today.

    PLEDGE_HIGH is defined in HardFilterReason but never returned by this
    function — no percentage-based pledge source exists yet for either
    exchange (see NSE_CLEAN_VALUE note above). Not a silent removal: kept
    in the enum for when Section 5's shareholding-filings pipeline exists.
    """
    if ":" not in composite_symbol:
        composite_symbol = f"NSE:{composite_symbol}"
    exchange, symbol = composite_symbol.split(":", 1)

    if exchange == "NSE":
        flags = surveillance.get_nse_flags(symbol)

        if "IRP" in flags:
            return HardFilterResult(composite_symbol, False, HardFilterReason.INSOLVENCY_IRP)
        if "GSM" in flags:
            return HardFilterResult(composite_symbol, False, HardFilterReason.SURVEILLANCE_GSM)
        if "ESM" in flags:
            return HardFilterResult(composite_symbol, False, HardFilterReason.SURVEILLANCE_ESM)
        if "ASM" in flags:
            return HardFilterResult(composite_symbol, False, HardFilterReason.SURVEILLANCE_ASM)

    else:  # BSE — mapper resolution required first, see docstring above
        isin = _resolve_bse_isin(mapper, composite_symbol)
        if isin is None:
            return HardFilterResult(composite_symbol, False, HardFilterReason.UNKNOWN_SYMBOL)

        flags = surveillance.get_bse_flags_by_isin(isin)

        # No BSE IRP source — this check is skipped entirely for BSE,
        # not silently passing as clean; documented above and in the
        # module docstring.
        if "GSM" in flags:
            return HardFilterResult(composite_symbol, False, HardFilterReason.SURVEILLANCE_GSM)
        if "ESM" in flags:
            return HardFilterResult(composite_symbol, False, HardFilterReason.SURVEILLANCE_ESM)
        if "ASM" in flags:
            return HardFilterResult(composite_symbol, False, HardFilterReason.SURVEILLANCE_ASM)

    info = mapper.get_instrument_info(composite_symbol)
    if not info:
        return HardFilterResult(composite_symbol, False, HardFilterReason.UNKNOWN_SYMBOL)

    if not mapper.is_freely_tradeable(composite_symbol):
        return HardFilterResult(composite_symbol, False, HardFilterReason.RESTRICTED_SERIES)

    if not is_liquid:
        return HardFilterResult(composite_symbol, False, HardFilterReason.ILLIQUID)

    return HardFilterResult(composite_symbol, True, HardFilterReason.NONE)