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


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        refresh_market_analysis,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=45)
    )
    scheduler.start()
    try:
        refresh_market_analysis()
    except Exception as e:
        print(f"Initial market refresh failed (will retry on next scheduled run): {e}")

