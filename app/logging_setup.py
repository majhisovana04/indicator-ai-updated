# app/logging_setup.py
import logging

logging.basicConfig(
    filename="app_activity.log",
    level=logging.INFO,
    format="%(asctime)s | %(message)s"
)
logger = logging.getLogger("indicator_bot")