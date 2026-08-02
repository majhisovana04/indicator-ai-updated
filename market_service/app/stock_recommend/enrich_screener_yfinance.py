import time
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from collections import OrderedDict
from market_service.app.stock_recommend.Screener_NSE_Bse import scrape_screener_index
from market_service.app.market.instrument_mapper import InstrumentMapper

HEADERS = {"User-Agent": "Mozilla/5.0 (Phase-1-fundamentals-fill)"}

def enrich_with_roe(combined: OrderedDict, mapper: InstrumentMapper) -> OrderedDict:
    """
    Takes the deduplicated Screener data and backfills ROE and EPS using yfinance.
    mapper is used to resolve BSE-only scrip codes (e.g. 544467) to real
    trading symbols (e.g. NSDL) via the scrip_code_to_symbol index.
    """
    for i, (cid, row) in enumerate(combined.items(), 1):
        href = row.get("symbol_href", "")
        parts = [p for p in href.split("/") if p]
        raw_sym = parts[1].upper() if len(parts) >= 2 else None
        
        if not raw_sym:
            print(f"  [warn] no symbol for company_id {cid}, skipping")
            continue

        if raw_sym.isdigit():
            # BSE-only scrip code (e.g. 544467 for NSDL).
            # Resolve to real trading symbol via reverse index.
            composite = mapper.scrip_code_to_symbol.get(raw_sym)  # e.g. 'BSE:NSDL'
            if composite:
                symbol = composite.split(":", 1)[1]  # strip 'BSE:' prefix
                yf_suffix = ".NS"  # try NSE first; yfinance will return None if not listed
            else:
                # Truly unresolvable scrip code — store as-is and try .BO
                symbol = raw_sym
                yf_suffix = ".BO"
                print(f"  [warn] scrip code {raw_sym} not found in InstrumentMapper")
        else:
            symbol = raw_sym
            yf_suffix = ".NS"
            
        row["nse_symbol"] = symbol

        ticker = yf.Ticker(f"{symbol}{yf_suffix}")
        try:
            row["roe"] = ticker.info.get("returnOnEquity")
            row["eps"] = ticker.info.get("trailingEps")
        except Exception as e:
            print(f"  [warn] yfinance failed for {symbol}: {e}")
            row["roe"] = None
            row["eps"] = None

        # BSE-only stocks (resolved from scrip code) won't have .NS listing.
        # If .NS returned None, retry with .BO suffix.
        if (row["roe"] is None or row["eps"] is None) and raw_sym.isdigit() and composite:
            try:
                bo_ticker = yf.Ticker(f"{symbol}.BO")
                if row["roe"] is None:
                    row["roe"] = bo_ticker.info.get("returnOnEquity")
                if row["eps"] is None:
                    row["eps"] = bo_ticker.info.get("trailingEps")
            except Exception:
                pass
            
        print(f"[{i}/{len(combined)}] {symbol} -> ROE = {row['roe']}, EPS = {row['eps']}")
        time.sleep(0.5)

    return combined

def _parse_ratio_panel(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    top_ratios = soup.find("ul", id="top-ratios")
    if not top_ratios:
        return {}
    ratios = {}
    for li in top_ratios.find_all("li"):
        name_el = li.find("span", class_="name")
        value_el = li.find("span", class_="value")
        if name_el and value_el:
            ratios[name_el.get_text(strip=True)] = value_el.get_text(strip=True).replace(",", "")
    return ratios

def scrape_screener_ratios(symbol: str) -> dict:
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
    except requests.RequestException as e:
        print(f"  [warn] could not fetch Screener page for {symbol}: {e}")
        return {}

    ratios = _parse_ratio_panel(resp.text)

    def _has_digits(s: str) -> bool:
        return any(c.isdigit() for c in s)

    no_market_cap = not _has_digits(ratios.get("Market Cap", ""))
    no_roe = not _has_digits(ratios.get("ROE", ""))

    if resp.status_code == 404 or no_market_cap or no_roe:
        try:
            fallback_url = f"https://www.screener.in/company/{symbol}/"
            resp = requests.get(fallback_url, headers=HEADERS, timeout=10)
            ratios = _parse_ratio_panel(resp.text)
        except requests.RequestException as e:
            print(f"  [warn] fallback fetch failed for {symbol}: {e}")

    return ratios

def _parse_pct(value_str: str):
    if not value_str:
        return None
    cleaned = value_str.replace("%", "").strip()
    try:
        return float(cleaned) / 100
    except ValueError:
        return None

def fill_missing_roe(combined: OrderedDict, missing_symbols: list) -> OrderedDict:
    """
    Fills ROE for exactly the symbols yfinance couldn't cover.
    Note: We do NOT fill EPS from Screener per strict user request.
    """
    filled, still_missing = 0, []

    print(f"\n--- Starting Screener.in fallback for {len(missing_symbols)} missing ROEs ---\n")
    
    for i, symbol in enumerate(missing_symbols, 1):
        if symbol.isdigit():
            print(f"[{i}/{len(missing_symbols)}] Skipping '{symbol}' (BSE Scrip Code fallback not fully supported here)")
            still_missing.append(symbol)
            continue

        ratios = scrape_screener_ratios(symbol)
        roe = _parse_pct(ratios.get("ROE"))

        found = False
        for row in combined.values():
            if row.get("nse_symbol") == symbol:
                row["roe"] = roe
                found = True
                break

        if roe is not None:
            filled += 1
            print(f"[{i}/{len(missing_symbols)}] {symbol} -> Screener ROE = {roe}")
        else:
            still_missing.append(symbol)
            print(f"[{i}/{len(missing_symbols)}] {symbol} -> ROE remains None (Genuinely unavailable)")

        if not found:
            print(f"  [warn] {symbol} not found in combined dict")

        time.sleep(2)  # politeness delay for Screener

    print(f"\nSuccessfully rescued {filled}/{len(missing_symbols)} via Screener.in!")
    print(f"{len(still_missing)} remain genuinely missing: {still_missing}")
    return combined

if __name__ == "__main__":
    import csv

    print("=" * 60)
    print("STAGE 0: Loading Instrument Mapper")
    print("=" * 60)
    mapper = InstrumentMapper()
    print(f"  Mapper loaded — {len(mapper.all_equity_symbols)} equities, "
          f"{len(mapper.scrip_code_to_symbol)} BSE scrip codes indexed.")

    print("\n" + "=" * 60)
    print("STAGE 1: Scraping Screener index pages (ROCE ONLY)")
    print("=" * 60)
    nifty500 = scrape_screener_index("CNX500")
    bse500 = scrape_screener_index("1005")
    print(f"  CNX500: {len(nifty500)} rows | 1005 (BSE 500): {len(bse500)} rows")

    print("\n" + "=" * 60)
    print("STAGE 2: Deduplicating by Screener company_id")
    print("=" * 60)
    combined = OrderedDict()
    for row in nifty500 + bse500:
        cid = row["company_id"]
        if cid not in combined:
            combined[cid] = row
    print(f"  Unique companies after dedupe: {len(combined)}")

    print("\n" + "=" * 60)
    print("STAGE 3: Enriching ROE and EPS via yfinance (~4 mins)")
    print("=" * 60)
    enriched_data = enrich_with_roe(combined, mapper)
    got_roe = sum(1 for r in enriched_data.values() if r.get("roe") is not None)
    got_eps = sum(1 for r in enriched_data.values() if r.get("eps") is not None)
    print(f"\n  yfinance pass complete: {got_roe}/{len(enriched_data)} ROEs filled.")
    print(f"  yfinance pass complete: {got_eps}/{len(enriched_data)} EPS filled.")

    missing_roe = [row["nse_symbol"] for row in enriched_data.values()
                   if row.get("roe") is None and row.get("nse_symbol")]
    if missing_roe:
        print("\n" + "=" * 60)
        print(f"STAGE 4: Screener.in fallback for {len(missing_roe)} missing ROEs")
        print("=" * 60)
        final_data = fill_missing_roe(enriched_data, missing_roe)
    else:
        print("\nSTAGE 4: Skipped — all ROEs filled by yfinance!")
        final_data = enriched_data

    print("\n" + "=" * 60)
    print("STAGE 5: Looking up ISIN from InstrumentMapper")
    print("=" * 60)
    isin_not_found = []
    for row in final_data.values():
        sym = row.get("nse_symbol")
        if not sym:
            row["isin"] = None
            continue

        info = mapper.get_instrument_info(f"NSE:{sym}")
        isin = info.get("isin")

        if not isin:
            info = mapper.get_instrument_info(f"BSE:{sym}")
            isin = info.get("isin")

        if not isin:
            print(f"  [warn] ISIN not found for symbol '{sym}' (company: {row.get('name')})")
            isin_not_found.append(sym)

        row["isin"] = isin

    print(f"  ISIN lookup complete: "
          f"{len(final_data) - len(isin_not_found)}/{len(final_data)} ISINs resolved.")

    print("\n" + "=" * 60)
    print("STAGE 6: Saving fundamentals_523.csv")
    print("=" * 60)
    out_path = "c:\\Xane Funds\\indicator\\market_service\\app\\stock_recommend\\fundamentals_523.csv"
    fieldnames = ["isin", "company_id", "name", "eps", "roce", "roe"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(final_data.values())
    print(f"  Saved {len(final_data)} rows to {out_path}")

    with_all = sum(1 for r in final_data.values()
                   if r.get("eps") and r.get("roce") and r.get("roe") is not None)
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Total companies:             {len(final_data)}")
    print(f"  With EPS + ROCE + ROE:       {with_all}")
