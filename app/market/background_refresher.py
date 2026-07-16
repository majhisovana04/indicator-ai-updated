# from datetime import datetime
# from apscheduler.schedulers.background import BackgroundScheduler
# from apscheduler.triggers.cron import CronTrigger
# from app.market.screener import Screener
# from app.market.market_summary import MarketSummaryGenerator
# from app.market.cache import SimpleCache

# screener = Screener()
# summary_generator = MarketSummaryGenerator()

# live_summary_cache = SimpleCache()

# def refresh_market_analysis():
#     print("Refreshing market analysis...")
#     candidates = screener.get_top_candidates()
#     sentiment = screener.get_market_sentiment(candidates)
#     summary_text = summary_generator.generate(candidates, sentiment)

#     live_summary_cache.set({
#         "answer": summary_text,
#         "sentiment": sentiment,
#         "computed_at": datetime.now().isoformat()
#     })
#     print("Market analysis refreshed.")


# def start_scheduler():
#     scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
#     scheduler.add_job(
#         refresh_market_analysis,
#         CronTrigger(day_of_week="mon-fri", hour=15, minute=45)
#     )
#     scheduler.start()
#     try:
#         refresh_market_analysis()
#     except Exception as e:
#         print(f"Initial market refresh failed (will retry on next scheduled run): {e}")

# app/market/background_refresher.py

from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.market.screener import Screener
from app.market.market_summary import MarketSummaryGenerator
from app.redis_client import get_redis
import json
from app.market.signal_matrix_scanner import SignalMatrixScanner
import json as _json
from app.market.market_pulse import compute_market_pulse, refresh_vix_only

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
        # Expires roughly before the next trading day starts (e.g. 20 hours)
        r.expire("market:daily_summary", 20 * 3600)
    print("Market analysis refreshed.")


signal_scanner = SignalMatrixScanner()
def refresh_signal_matrix():
    print("Refreshing Nifty 50 signal matrix...")
    matrix = signal_scanner.scan_index("nifty50")

    r = get_redis()
    if r:
        r.set("signal_matrix:nifty50", _json.dumps(matrix))
        r.expire("signal_matrix:nifty50", 20 * 3600)  # same 20h pattern as daily_summary
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
        r.expire("market_pulse:nifty50", 20 * 3600)
    print(f"Market pulse refreshed: {pulse['mood']}, VIX={pulse['volatility']['vix_value']}")




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
    
    scheduler.start()
    try:
        refresh_market_analysis()
        refresh_signal_matrix()
        refresh_market_pulse()
       
    except Exception as e:
        print(f"Initial market refresh failed (will retry on next scheduled run): {e}")

