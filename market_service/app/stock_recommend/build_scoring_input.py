import csv

# ── 1. Load the merged fundamentals we just created ──
def load_fundamentals(path="fundamentals_523.csv") -> dict:
    """Returns {isin: {eps, roce, roe, name}}"""
    table = {}
    skipped = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            isin = row.get("isin", "").strip()
            if not isin:
                skipped += 1
                continue
            table[isin] = {
                "eps": row["eps"], "roce": row["roce"], "roe": row["roe"], "name": row["name"],
            }
    if skipped:
        print(f"[warn] {skipped} fundamentals rows had no ISIN — excluded from join table")
    return table

# ── 2. Load the official Nifty 500 list ──
def load_nse_universe(path="ind_nifty500list.csv") -> list:
    """Returns list of {symbol, isin} from the official NSE CSV."""
    with open(path, encoding="utf-8-sig") as f:
        return [{"symbol": r["Symbol"], "isin": r["ISIN Code"]} for r in csv.DictReader(f)]

# ── 3. Load the official BSE 500 list ──
def load_bse_universe(path="BSE 500Index_Constituents.csv") -> list:
    """Returns list of {scrip_code, isin} from the official BSE CSV."""
    with open(path, encoding="utf-8-sig") as f:
        return [{"scrip_code": r["Scrip Code"], "isin": r["ISIN No."]} for r in csv.DictReader(f)]

# ── 4. The Merge Logic ──
def build_scoring_input(exchange: str, universe: list, fundamentals: dict) -> list:
    """
    Joins each exchange's listing list against the shared fundamentals
    table by ISIN. A dual-listed company gets the SAME fundamentals row
    whether it's being scored for NSE or BSE — fetched once, used twice.
    """
    rows = []
    missing = []
    for entry in universe:
        isin = entry["isin"]
        fund = fundamentals.get(isin)
        
        if fund is None:
            missing.append(entry)
            continue
            
        # Combine the original exchange entry (like symbol) with the fundamentals
        rows.append({**entry, **fund, "exchange": exchange})

    if missing:
        print(f"[{exchange}] {len(missing)} symbols have no fundamentals match — "
              f"check ISIN alignment: {[m.get('symbol') or m.get('scrip_code') for m in missing[:5]]}")

    return rows

if __name__ == "__main__":
    print("Loading fundamentals table...")
    fundamentals = load_fundamentals("fundamentals_523.csv")
    
    print("Joining NSE universe...")
    nse_scoring_input = build_scoring_input("NSE", load_nse_universe(), fundamentals)
    
    print("Joining BSE universe...")
    bse_scoring_input = build_scoring_input("BSE", load_bse_universe(), fundamentals)

    print("\n=== Join Results ===")
    print(f"NSE candidates with fundamentals: {len(nse_scoring_input)}/500")
    print(f"BSE candidates with fundamentals: {len(bse_scoring_input)}/501")
    
    # Optional: peek at the first joined record
    print("\nSample Joined Record (NSE):")
    print(nse_scoring_input[0])
