import pandas as pd

MIN_SECTOR_SIZE = 3

def percentile_rank(series: pd.Series) -> pd.Series:
    """Calculates the 0-100 percentile rank of a series."""
    return series.rank(pct=True) * 100

def sector_relative_percentile(df: pd.DataFrame, col: str) -> pd.Series:
    """
    Ranks stocks within their own sector.
    If a sector has fewer than MIN_SECTOR_SIZE stocks, it falls back to ranking
    them against the entire sample to prevent math distortion (e.g., a sector
    with 1 stock always getting 100%).
    """
    if "sector" not in df.columns:
        raise ValueError("DataFrame must have a 'sector' column")
        
    sector_counts = df["sector"].value_counts()
    too_small = df["sector"].map(sector_counts) < MIN_SECTOR_SIZE
    
    result = df.groupby("sector")[col].rank(pct=True) * 100
    
    if too_small.any():
        whole_sample_rank = percentile_rank(df[col])
        result[too_small] = whole_sample_rank[too_small]
        
    return result

def compute_composite_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Takes a DataFrame of candidates enriched with fundamentals and momentum,
    calculates percentile ranks across the universe, and generates the final
    0-100 composite scores for short, mid, and long horizons.
    """
    df = df.copy()

    # The fundamentals are loaded from a CSV, so they might be strings.
    # Convert them to numeric (turning empty strings or invalid data into NaN).
    for col in ["realtime_pe", "roce", "roe"]:
        if col in df.columns:
            # Handle cases where "%" might be trailing on ROCE/ROE strings
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace("%", "", regex=False)
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # ── 1. Quality (Higher ROCE and ROE is better) ──
    if df["roce"].notna().any() or df["roe"].notna().any():
        # Fill missing values with the sector median
        roce_filled = df.groupby("sector")["roce"].transform(lambda s: s.fillna(s.median()))
        roe_filled = df.groupby("sector")["roe"].transform(lambda s: s.fillna(s.median()))
        
        df["quality_score"] = (
            sector_relative_percentile(df.assign(roce=roce_filled), "roce") + 
            sector_relative_percentile(df.assign(roe=roe_filled), "roe")
        ) / 2
    else:
        df["quality_score"] = 0

    # ── 2. Valuation (Lower P/E is better, so invert the rank: 100 - rank) ──
    if df["realtime_pe"].notna().any():
        df["valuation_score"] = 100 - sector_relative_percentile(df, "realtime_pe")
    else:
        df["valuation_score"] = 0

    # ── 3. Momentum (Rank the raw scores from Stage 5) ──
    df["momentum_score_short"] = percentile_rank(df["momentum_raw_short"].fillna(0))
    df["momentum_score_mid"] = percentile_rank(df["momentum_raw_mid"].fillna(0))
    df["momentum_score_long"] = percentile_rank(df["momentum_raw_long"].fillna(0))

    # ── 4. Apply Re-Normalized Weights ──
    # Sentiment is only included when real signals were present (signals_used > 0).
    # When absent, its weight is redistributed proportionally to the other three
    # components — same renormalization pattern used for Quality/Valuation above.

    if "sentiment_score" not in df.columns:
        df["sentiment_score"] = 0.0
    if "sentiment_signals" not in df.columns:
        df["sentiment_signals"] = 0

    has_sentiment = df["sentiment_signals"] > 0

    # Short Term base weights: Quality 20%, Valuation 20%, Momentum 45%, Sentiment 15%
    # When sentiment absent → redistribute 15% proportionally: Q=23.5%, V=23.5%, M=53%
    df["composite_short"] = (
        df.apply(lambda r: (
            r["quality_score"] * 0.20 +
            r["valuation_score"] * 0.20 +
            r["momentum_score_short"] * 0.45 +
            r["sentiment_score"] * 0.15
        ) if r["sentiment_signals"] > 0 else (
            r["quality_score"] * 0.235 +
            r["valuation_score"] * 0.235 +
            r["momentum_score_short"] * 0.530
        ), axis=1)
    )

    # Mid Term base weights: Quality 40%, Valuation 30%, Momentum 20%, Sentiment 10%
    # When sentiment absent → redistribute 10%: Q=44.4%, V=33.3%, M=22.2%
    df["composite_mid"] = (
        df.apply(lambda r: (
            r["quality_score"] * 0.40 +
            r["valuation_score"] * 0.30 +
            r["momentum_score_mid"] * 0.20 +
            r["sentiment_score"] * 0.10
        ) if r["sentiment_signals"] > 0 else (
            r["quality_score"] * 0.444 +
            r["valuation_score"] * 0.333 +
            r["momentum_score_mid"] * 0.222
        ), axis=1)
    )

    # Long Term: Quality 55.5%, Valuation 33.3%, Momentum 11.1% — unchanged
    df["composite_long"] = (
        (df["quality_score"].fillna(0) * 0.555) +
        (df["valuation_score"].fillna(0) * 0.333) +
        (df["momentum_score_long"].fillna(0) * 0.111)
    )

    return df

