# app/logging_setup.py
import logging
import sys

logging.basicConfig(
    # filename="app_activity.log",
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s | %(message)s"
)
logger = logging.getLogger("indicator_bot")