#app.market.background_refresher.py
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from market_service.app.market.screener import Screener
from market_service.app.market.market_summary import MarketSummaryGenerator
from market_service.app.stock_recommend.daily_pipeline import run_stock_recommendation_pipeline
from core_shared.redis_client import get_redis
import json
from market_service.app.market.signal_matrix_scanner import SignalMatrixScanner
import json as _json
from market_service.app.market.market_pulse import compute_market_pulse, refresh_vix_only
import requests
import os

screener = Screener()
summary_generator = MarketSummaryGenerator()

# We no longer use in-memory SimpleCache because the scheduler
# runs in a separate process from the web workers. We use Redis instead.

def refresh_market_analysis():
    print("Refreshing market analysis...")
    candidates = screener.get_top_candidates()
    sentiment = screener.get_market_sentiment(candidates)
    summary_text = summary_generator.generate(candidates, sentiment)

    summary_data = {
        "answer": summary_text,
        "sentiment": sentiment,
        "computed_at": datetime.now().isoformat()
    }
    
    r = get_redis()
    if r:
        r.set("market:daily_summary", json.dumps(summary_data))
        # Keep until the next run overwrites it (3 days to cover weekends)
        r.expire("market:daily_summary", 3 * 24 * 3600)
    print("Market analysis refreshed.")


signal_scanner = SignalMatrixScanner()
def refresh_signal_matrix():
    print("Refreshing Nifty 50 signal matrix...")
    matrix = signal_scanner.scan_index("nifty50")

    r = get_redis()
    if r:
        r.set("signal_matrix:nifty50", _json.dumps(matrix))
        r.expire("signal_matrix:nifty50", 3 * 24 * 3600)  # Keep for 3 days to cover weekends
    print(f"Signal matrix refreshed: {len(matrix)} symbols stored.")


def refresh_market_pulse():
    print("Refreshing market pulse...")
    r = get_redis()
    raw_matrix = r.get("signal_matrix:nifty50") if r else None
    if not raw_matrix:
        print("[MarketPulse] No signal matrix available yet, skipping pulse refresh.")
        return

    matrix = _json.loads(raw_matrix)
    pulse = compute_market_pulse(matrix)

    if r:
        r.set("market_pulse:nifty50", _json.dumps(pulse))
        r.expire("market_pulse:nifty50", 3 * 24 * 3600)
    print(f"Market pulse refreshed: {pulse['mood']}, VIX={pulse['volatility']['vix_value']}")


def refresh_daily_pipeline():
    print("Starting daily momentum pipeline (runs for ~35 minutes)...")
    try:
        run_stock_recommendation_pipeline()
        r = get_redis()
        if r:
            r.set("pipeline:last_success", datetime.now().isoformat())
        print("Daily stock recommendation(quality, valuation, momentum) pipeline completed successfully.")
    except Exception as e:
        print(f"Daily pipeline failed: {e}")
        # Cheapest possible alert — a webhook to Slack/Discord/email.
        alert_url = os.environ.get("ALERT_WEBHOOK_URL", "")
        if alert_url:
            try:
                requests.post(alert_url, json={"text": f"Daily pipeline failed: {e}"}, timeout=5)
            except Exception:
                pass  # don't let alerting itself crash the scheduler


def retry_if_stale_today():
    r = get_redis()
    last_success = r.get("pipeline:last_success") if r else None
    if last_success and datetime.fromisoformat(last_success).date() == datetime.now().date():
        return  # already succeeded today, skip
    print("19:00 run appears to have failed — retrying...")
    refresh_daily_pipeline()

def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        refresh_market_analysis,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=45)
    )
    scheduler.add_job(
        refresh_signal_matrix,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=50)   # staggered 5 min after, avoids overlapping API bursts
    )
    scheduler.add_job(
        refresh_market_pulse,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=55)  # 5 min after signal matrix
    )
    # scheduler — add alongside your existing jobs
    scheduler.add_job(
        refresh_vix_only,
        CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/15")
    )
    
    # Run the heavy 35-minute momentum pipeline exactly once a day,
    # well after the market closes (7:00 PM IST).
    scheduler.add_job(
        refresh_daily_pipeline,
        CronTrigger(day_of_week="mon-fri", hour=19, minute=0)
    )
    
    # Cheap safety net: retry once more later the same evening if the 19:00
    # run failed. Only actually re-runs the expensive 35-min job if today's
    # rankings weren't updated.
    scheduler.add_job(
        retry_if_stale_today,
        CronTrigger(day_of_week="mon-fri", hour=21, minute=30)
    )
    scheduler.start()
    try:
        refresh_market_analysis()
        refresh_signal_matrix()
        refresh_market_pulse()
       
    except Exception as e:
        print(f"Initial market refresh failed (will retry on next scheduled run): {e}")

