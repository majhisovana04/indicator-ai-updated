# run_scheduler.py
import time
from dotenv import load_dotenv
load_dotenv()

from app.market.background_refresher import start_scheduler

if __name__ == "__main__":
    print("============================================================")
    print("INDICATOR AI — STANDALONE BACKGROUND SCHEDULER")
    print("============================================================")
    print("This script runs the daily market refresher completely")
    print("independent of the web workers. It prevents duplicate runs")
    print("and Gunicorn worker timeouts.")
    print("============================================================")
    print("Starting scheduler... (Press Ctrl+C to exit)\n")
    
    start_scheduler()
    
    # Keep the main thread alive since APScheduler runs in the background
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nStopping scheduler...")
