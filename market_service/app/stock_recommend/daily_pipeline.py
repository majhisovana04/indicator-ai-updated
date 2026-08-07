import sys
import time
import pandas as pd
from typing import List, Dict

from market_service.app.market.instrument_mapper import InstrumentMapper
from market_service.app.market.fetch_all_surveillance import DailySurveillanceFetcher
from market_service.app.market.hard_filters import check_hard_filters, HardFilterResult
from market_service.app.market.upstox_client import UpstoxClient
from market_service.app.market.signal_engine import compute_horizon_signal_matrix
from market_service.app.market.scoring_utils import compute_composite_scores
from market_service.app.stock_recommend.sentiment_engine import (
    fetch_fii_dii_signal,
    compute_sentiment_score,
    compute_news_scores_for_shortlist,
)
from core_shared.redis_client import get_redis
import json
from market_service.app.stock_recommend.build_scoring_input import (
    load_fundamentals,
    load_nse_universe,
    load_bse_universe,
    build_scoring_input
)

# Polite delay between Upstox API calls — same value used in phase0_validate.py
# Keeps us well under rate-limit thresholds (~500 requests per run).
REQUEST_DELAY_SECONDS = 2.0

def run_stock_recommendation_pipeline():
    print("=" * 60)
    print("STARTING DAILY PIPELINE (Stages 1-5)")
    print("=" * 60)

    import os
    from datetime import datetime
    base_dir = os.path.dirname(__file__)
    cache_dir = os.path.join(base_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    cache_file = os.path.join(cache_dir, f"momentum_cache_{today_str}.json")

    # -------------------------------------------------------------------------
    # STAGE 1: Load Universe
    # -------------------------------------------------------------------------
    print("\n[Stage 1] Loading Universe and Mappers...")
    mapper = InstrumentMapper()
    
    nse_csv = os.path.join(base_dir, "ind_nifty500list.csv")
    bse_csv = os.path.join(base_dir, "BSE 500Index_Constituents.csv")
    fund_csv = os.path.join(base_dir, "fundamentals_523.csv")
    
    nse_universe_raw = load_nse_universe(nse_csv)
    bse_universe_raw = load_bse_universe(bse_csv)
    
    print(f"  Loaded {len(nse_universe_raw)} NSE symbols from Nifty 500")
    print(f"  Loaded {len(bse_universe_raw)} BSE scrip codes from BSE 500")

    # We also need a fast lookup to grab Nifty 500's 'Industry' column as our sector
    import csv
    isin_to_sector = {}
    with open(nse_csv, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            isin_to_sector[r["ISIN Code"]] = r.get("Industry", "Unknown")

    # -------------------------------------------------------------------------
    # STAGE 2: Fundamentals (Loaded from slow-batch cache)
    # -------------------------------------------------------------------------
    print("\n[Stage 2] Loading cached fundamentals (ISIN-keyed)...")
    fundamentals = load_fundamentals(fund_csv)
    print(f"  Loaded {len(fundamentals)} unique companies' fundamentals")

    # -------------------------------------------------------------------------
    # STAGE 3: Join fundamentals into each exchange's universe
    # -------------------------------------------------------------------------
    print("\n[Stage 3] Joining fundamentals...")
    nse_candidates = build_scoring_input("NSE", nse_universe_raw, fundamentals)
    bse_candidates = build_scoring_input("BSE", bse_universe_raw, fundamentals)
    
    # Stamp the sector onto each candidate
    for cand in nse_candidates + bse_candidates:
        cand["sector"] = isin_to_sector.get(cand["isin"], "Unknown")
        
    print(f"  NSE candidates with fundamentals attached: {len(nse_candidates)}")
    print(f"  BSE candidates with fundamentals attached: {len(bse_candidates)}")

    # -------------------------------------------------------------------------
    # STAGE 4: Hard Filters (per exchange)
    # -------------------------------------------------------------------------
    print("\n[Stage 4] Running Hard Filters...")
    print("  Fetching surveillance files...")
    surveillance_fetcher = DailySurveillanceFetcher()
    surveillance = surveillance_fetcher.fetch_and_load()
    
    passed_nse = []
    passed_bse = []
    failed_counts = {}

    print("  Filtering NSE candidates...")
    for row in nse_candidates:
        sym = f"NSE:{row['symbol']}"
        res = check_hard_filters(sym, True, mapper, surveillance) # is_liquid=True for now, checked in Stage 5
        if res.passed:
            row["composite_symbol"] = sym
            passed_nse.append(row)
        else:
            reason = res.reason.display_text()
            failed_counts[reason] = failed_counts.get(reason, 0) + 1

    print("  Filtering BSE candidates...")
    for row in bse_candidates:
        scrip = str(row['scrip_code'])
        comp_sym = mapper.scrip_code_to_symbol.get(scrip)
        if not comp_sym:
            failed_counts["UNMAPPED_BSE_SCRIP"] = failed_counts.get("UNMAPPED_BSE_SCRIP", 0) + 1
            continue

        sym = comp_sym.split(":", 1)[1]
        res = check_hard_filters(comp_sym, True, mapper, surveillance)
        if res.passed:
            row["composite_symbol"] = comp_sym
            row["symbol"] = sym
            passed_bse.append(row)
        else:
            reason = res.reason.display_text()
            failed_counts[reason] = failed_counts.get(reason, 0) + 1

    print(f"\n  Final NSE count surviving hard filters: {len(passed_nse)} / {len(nse_candidates)}")
    print(f"  Final BSE count surviving hard filters: {len(passed_bse)} / {len(bse_candidates)}")
    
    if failed_counts:
        print("\n  Failures Breakdown:")
        for r, c in failed_counts.items():
            print(f"    - {r}: {c}")

    print("\n=== Stages 1-4 Complete! ===")

    # -------------------------------------------------------------------------
    # STAGE 5: Momentum Fetch (per exchange listing, NOT deduplicated)
    # -------------------------------------------------------------------------
    # Per the v4 Addendum Section 5: a dual-listed company gets computed TWICE
    # here — once with its NSE symbol, once with its BSE symbol — because
    # liquidity and price action genuinely differ by exchange. This is correct.
    #
    # Logic mirrors get_momentum_scores_all_horizons() from phase0_validate.py:
    #   fetch_ohlc(days=180) → compute_horizon_signal_matrix x3 → store scores
    # Per-horizon liquidity filter applied here: if is_liquid_{horizon} is False
    # for a given horizon, that stock is excluded from THAT horizon's list only.
    print("\n[Stage 5] Fetching Momentum (Upstox OHLC → signal engine)...")
    print(f"  Will process {len(passed_nse)} NSE + {len(passed_bse)} BSE candidates")
    print(f"  Estimated time: ~{int((len(passed_nse) + len(passed_bse)) * REQUEST_DELAY_SECONDS / 60)} minutes")

    client = UpstoxClient()

    def _fetch_momentum(candidates: list, exchange_label: str) -> list:
        """
        For each candidate that passed hard filters, fetch 180 days of OHLC
        from Upstox and compute short/mid/long horizon momentum scores.
        Returns a list of rows enriched with momentum fields.
        Rows are still kept even if some horizons are illiquid — the per-horizon
        liquidity flag is what controls inclusion at Stage 7 rank time.
        """
        enriched = []
        total = len(candidates)
        api_errors = 0
        insufficient_history = 0

        for i, row in enumerate(candidates, 1):
            sym = row["composite_symbol"]  # e.g. "NSE:RELIANCE" or "BSE:RELIANCE"

            if i % 50 == 0 or i == 1:
                print(f"  [{exchange_label}] {i}/{total} — last: {sym}")

            # ── Fetch OHLC (same as phase0_validate.py: days=180, which
            #    internally fetches 360 calendar days to get ~250 trading days,
            #    enough for SMA200 in the 'long' horizon weight profile)
            try:
                df_ohlc = client.fetch_ohlc(sym, days=180)
            except Exception as e:
                print(f"  [warn] Upstox fetch failed for {sym}: {e}", file=sys.stderr)
                api_errors += 1
                time.sleep(REQUEST_DELAY_SECONDS)
                continue  # Skip this stock entirely — no OHLC data

            # Require at least 50 trading-day rows (enough for short/mid term SMA50/EMA20).
            # If it has <200 rows, long-term SMA200 will naturally evaluate to NaN,
            # and the signal engine is already designed to gracefully ignore missing 
            # indicators and re-normalize the remaining weights!
            if df_ohlc.empty or len(df_ohlc) < 50:
                print(f"  [warn] insufficient price history for {sym} ({len(df_ohlc)} rows) — skipping", file=sys.stderr)
                insufficient_history += 1
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            # ── Calculate Real-Time P/E ────────────────────────────────────────
            current_price = float(df_ohlc["close"].iloc[-1])
            eps = row.get("eps")
            if eps is None or str(eps).strip() == "" or float(eps) <= 0:
                row["realtime_pe"] = None   # missing EPS → excluded from valuation scoring
            else:
                row["realtime_pe"] = round(current_price / float(eps), 2)


            # ── Compute all 3 horizons — same loop as phase0_validate.py ──────
            horizon_scores = {}
            for horizon in ["short", "mid", "long"]:
                # STRICT HORIZON GUARD: Do not allow a young stock to receive a 
                # long-term score purely by renormalizing its short-term indicators. 
                # If it doesn't have 200 days of history, it CANNOT have a long-term trend.
                if horizon == "long" and len(df_ohlc) < 200:
                    horizon_scores[horizon] = {"score": None, "is_liquid": False, "ai_signal": "insufficient_data"}
                    continue
                if horizon == "mid" and len(df_ohlc) < 50:
                    horizon_scores[horizon] = {"score": None, "is_liquid": False, "ai_signal": "insufficient_data"}
                    continue

                try:
                    result = compute_horizon_signal_matrix(sym, df_ohlc, horizon=horizon)
                    horizon_scores[horizon] = {
                        "score": float(result["score"]),
                        "is_liquid": bool(result["is_liquid"]),
                        "ai_signal": result["ai_signal"],
                    }
                except Exception as e:
                    print(f"  [warn] signal_engine failed for {sym} [{horizon}]: {e}", file=sys.stderr)
                    horizon_scores[horizon] = {"score": None, "is_liquid": False, "ai_signal": "error"}

            # ── Stamp momentum fields onto the row (same field names as phase0) ─
            row["momentum_raw_short"] = horizon_scores["short"]["score"]
            row["momentum_raw_mid"]   = horizon_scores["mid"]["score"]
            row["momentum_raw_long"]  = horizon_scores["long"]["score"]
            row["is_liquid_short"]    = horizon_scores["short"]["is_liquid"]
            row["is_liquid_mid"]      = horizon_scores["mid"]["is_liquid"]
            row["is_liquid_long"]     = horizon_scores["long"]["is_liquid"]

            enriched.append(row)

            # Polite delay — same as phase0_validate.py (2.0s)
            time.sleep(REQUEST_DELAY_SECONDS)

        print(f"  [{exchange_label}] Done. Enriched: {len(enriched)}/{total} "
              f"(api_errors={api_errors}, insufficient_history={insufficient_history})")
        return enriched

    print("\n  --- Fetching NSE momentum ---")
    nse_momentum = _fetch_momentum(passed_nse, "NSE")

    print("\n  --- Fetching BSE momentum ---")
    bse_momentum = _fetch_momentum(passed_bse, "BSE")

    # ── Per-horizon liquidity breakdown (useful to see how many survive each horizon)
    for exchange_label, momentum_list in [("NSE", nse_momentum), ("BSE", bse_momentum)]:
        for horizon in ["short", "mid", "long"]:
            liquid_count = sum(1 for r in momentum_list if r.get(f"is_liquid_{horizon}"))
            print(f"  [{exchange_label}] Liquid for {horizon}: {liquid_count}/{len(momentum_list)}")

    print("\n=== Stage 5 Complete! ===")
    print(f"  NSE survivors with momentum: {len(nse_momentum)}")
    print(f"  BSE survivors with momentum: {len(bse_momentum)}")

    # Save to local cache for fast reruns on the same day
    print(f"  Saving to cache: {cache_file}")
    with open(cache_file, "w") as f:
        json.dump({"nse_momentum": nse_momentum, "bse_momentum": bse_momentum}, f)

    # -------------------------------------------------------------------------
    # STAGE 6a: Compute Initial Composite Scores (No Sentiment)
    # -------------------------------------------------------------------------
    print("\n[Stage 6a] Calculating Initial Composite Scores (Q + V + M)...")
    
    df_nse = pd.DataFrame(nse_momentum)
    df_bse = pd.DataFrame(bse_momentum)

    df_nse = compute_composite_scores(df_nse)
    df_bse = compute_composite_scores(df_bse)

    # -------------------------------------------------------------------------
    # STAGE 6b: Shortlist Top 75 per Horizon
    # -------------------------------------------------------------------------
    print("\n[Stage 6b] Shortlisting Top 75 candidates for Sentiment Enrichment...")

    def _get_shortlist(df: pd.DataFrame, limit: int = 75) -> set:
        shortlist = set()
        for horizon in ["short", "mid", "long"]:
            if f"composite_{horizon}" in df.columns and f"is_liquid_{horizon}" in df.columns:
                mask = df[f"is_liquid_{horizon}"] & df[f"composite_{horizon}"].notna()
                top_syms = df[mask].sort_values(by=f"composite_{horizon}", ascending=False).head(limit)["composite_symbol"]
                shortlist.update(top_syms.tolist())
        return shortlist

    nse_shortlist = _get_shortlist(df_nse)
    bse_shortlist = _get_shortlist(df_bse)
    full_shortlist = list(nse_shortlist | bse_shortlist)

    print(f"  Shortlisted {len(full_shortlist)} unique stocks across all horizons.")

    # -------------------------------------------------------------------------
    # STAGE 6c: Fetch News for Shortlist in Batch
    # -------------------------------------------------------------------------
    print("\n[Stage 6c] Fetching and Scoring News for Shortlist...")
    news_scores = compute_news_scores_for_shortlist(full_shortlist, mapper)

    # -------------------------------------------------------------------------
    # STAGE 6d: Sentiment Enrichment
    # -------------------------------------------------------------------------
    print("\n[Stage 6d] Computing Full Sentiment Scores...")

    fii_dii_score = fetch_fii_dii_signal()
    if fii_dii_score is not None:
        print(f"  FII/DII signal: {fii_dii_score:+.3f}")
    else:
        print("  FII/DII signal: unavailable (will use 0.0 for all stocks)")

    sentiment_errors = 0
    oi_cache: dict[str, float | None] = {}

    def _apply_sentiment(df: pd.DataFrame, shortlist: set):
        nonlocal sentiment_errors
        
        # Initialize default sentiment columns
        df["sentiment_score"] = 0.0
        df["sentiment_fii_dii"] = "N/A"
        df["sentiment_oi_trend"] = "N/A"
        df["sentiment_news"] = "N/A"
        df["sentiment_signals"] = 0
        
        for idx, row in df.iterrows():
            sym = row["composite_symbol"]
            if sym not in shortlist:
                continue

            try:
                underlying = sym.split(":", 1)[1] if ":" in sym else sym
                news_score = news_scores.get(sym)

                sentiment = compute_sentiment_score(
                    symbol=sym,
                    mapper=mapper,
                    fii_dii_score=fii_dii_score,
                    news_score=news_score,
                    oi_cache=oi_cache,
                    underlying=underlying,
                )
                df.at[idx, "sentiment_score"] = sentiment["score"]
                df.at[idx, "sentiment_fii_dii"] = sentiment["fii_dii"]
                df.at[idx, "sentiment_oi_trend"] = sentiment["oi_trend"]
                df.at[idx, "sentiment_news"] = sentiment["news"]
                df.at[idx, "sentiment_signals"] = sentiment["signals_used"]
            except Exception as e:
                print(f"  [warn] sentiment failed for {sym}: {e}")
                sentiment_errors += 1
            
            # Polite delay only when making Upstox OI calls
            time.sleep(REQUEST_DELAY_SECONDS)
        
        return df

    df_nse = _apply_sentiment(df_nse, nse_shortlist)
    df_bse = _apply_sentiment(df_bse, bse_shortlist)

    print(f"  Stage 6d complete: {len(full_shortlist) - sentiment_errors}/{len(full_shortlist)} shortlisted stocks scored successfully.")

    # -------------------------------------------------------------------------
    # STAGE 6e: Re-Calculate Composite Scores (With Sentiment)
    # -------------------------------------------------------------------------
    print("\n[Stage 6e] Re-Calculating Composite Scores with Sentiment...")
    df_nse = compute_composite_scores(df_nse)
    df_bse = compute_composite_scores(df_bse)

    print("  Scoring math applied successfully.")

    # -------------------------------------------------------------------------
    # STAGE 7: Rank and Select (Top 10 per horizon per exchange)
    # -------------------------------------------------------------------------
    print("\n[Stage 7] Ranking and Selecting Top 10...")

    def _get_top_10(df: pd.DataFrame, horizon: str) -> list:
        # 1. Filter out illiquid stocks for THIS specific horizon
        # 2. Filter out stocks that were skipped due to insufficient history (score is None/NaN)
        liquid_mask = df[f"is_liquid_{horizon}"] == True
        valid_score_mask = df[f"composite_{horizon}"].notna()
        
        valid_df = df[liquid_mask & valid_score_mask]

        # 3. Sort descending by composite score
        top_10_df = valid_df.sort_values(by=f"composite_{horizon}", ascending=False).head(10)

        # 4. Format into clean dictionaries for storage
        now_timestamp = pd.Timestamp.now(tz="Asia/Kolkata").strftime('%Y-%m-%d %H:%M:%S')
        results = []
        for _, row in top_10_df.iterrows():
            results.append({
                "symbol": row["symbol"],
                "timestamp": now_timestamp,
                "composite_symbol": row["composite_symbol"],
                "company_name": row["name"],
                "isin": row["isin"],
                "sector": row["sector"],
                "score": round(float(row[f"composite_{horizon}"]), 2),
                "pe": round(float(row["realtime_pe"]), 2) if pd.notna(row["realtime_pe"]) else None,
                "roce": round(float(row["roce"]), 2) if pd.notna(row["roce"]) else None,
                "roe": round(float(row["roe"]) * 100, 2) if pd.notna(row["roe"]) else None,
                "sentiment": {
                    "score": round(float(row.get("sentiment_score", 0.0)), 3),
                    "fii_dii": row.get("sentiment_fii_dii", "N/A"),
                    "oi_trend": row.get("sentiment_oi_trend", "N/A"),
                    "news": row.get("sentiment_news", "N/A"),
                    "signals_used": int(row.get("sentiment_signals", 0)),
                },
            })
        return results

    nse_rankings = {
        "short_term": _get_top_10(df_nse, "short"),
        "mid_term": _get_top_10(df_nse, "mid"),
        "long_term": _get_top_10(df_nse, "long"),
    }

    bse_rankings = {
        "short_term": _get_top_10(df_bse, "short"),
        "mid_term": _get_top_10(df_bse, "mid"),
        "long_term": _get_top_10(df_bse, "long"),
    }

    print(f"  NSE: {len(nse_rankings['short_term'])} short, {len(nse_rankings['mid_term'])} mid, {len(nse_rankings['long_term'])} long.")
    print(f"  BSE: {len(bse_rankings['short_term'])} short, {len(bse_rankings['mid_term'])} mid, {len(bse_rankings['long_term'])} long.")

    # -------------------------------------------------------------------------
    # STAGE 8: Store to Redis
    # -------------------------------------------------------------------------
    print("\n[Stage 8] Storing rankings to Redis...")
    r = get_redis()
    if r is None:
        print("  [ERROR] Redis client unavailable! Skipping storage.")
    else:
        now_str = pd.Timestamp.now(tz="Asia/Kolkata").isoformat()
        
        nse_payload = {"updated_at": now_str, "rankings": nse_rankings}
        bse_payload = {"updated_at": now_str, "rankings": bse_rankings}

        r.set("rankings:NSE", json.dumps(nse_payload))
        r.set("rankings:BSE", json.dumps(bse_payload))
        print("  Successfully updated 'rankings:NSE' and 'rankings:BSE'.")

    print("\n=== PIPELINE COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_stock_recommendation_pipeline()
