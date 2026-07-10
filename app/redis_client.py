# app/redis_client.py
"""
Central Redis connection module.
All other modules import from here — connection is created ONCE.

Uses Upstash Redis (free tier, serverless, no self-hosting needed).
If Redis is unavailable, get_redis() returns None so callers can
gracefully degrade to in-memory fallback instead of crashing.
"""

import os
from dotenv import load_dotenv

load_dotenv()

_redis_client = None  # singleton — created once on first call


def get_redis():
    """
    Returns the shared Redis client, or None if connection fails.
    Callers must always handle the None case — Redis being down
    should degrade gracefully, never crash the app.
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    url = os.getenv("UPSTASH_REDIS_URL")
    token = os.getenv("UPSTASH_REDIS_TOKEN")

    if not url or not token:
        print("[Redis] WARNING: UPSTASH_REDIS_URL or UPSTASH_REDIS_TOKEN not set. Redis disabled.")
        return None

    try:
        from upstash_redis import Redis
        _redis_client = Redis(url=url, token=token)
        # Quick connectivity check
        _redis_client.ping()
        print("[Redis] Connected successfully.")
        return _redis_client
    except Exception as e:
        print(f"[Redis] WARNING: Could not connect — {e}. Redis disabled.")
        return None
