from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.market.screener import Screener
from app.market.market_summary import MarketSummaryGenerator
from app.market.cache import SimpleCache

screener = Screener()
summary_generator = MarketSummaryGenerator()

# TTL longer than 24h so it survives until the next scheduled run
live_summary_cache = SimpleCache(ttl_seconds=90000)


def refresh_market_analysis():
    print("Refreshing market analysis...")
    candidates = screener.get_top_candidates()
    sentiment = screener.get_market_sentiment(candidates)
    summary_text = summary_generator.generate(candidates, sentiment)

    live_summary_cache.set({
        "answer": summary_text,
        "sentiment": sentiment,
        "computed_at": datetime.now().isoformat()
    })
    print("Market analysis refreshed.")


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        refresh_market_analysis,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=45)
    )
    scheduler.start()
    refresh_market_analysis()  # run once immediately so there's data right away