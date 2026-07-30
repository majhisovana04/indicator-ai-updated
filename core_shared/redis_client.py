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

_redis_client = None  # Market Redis singleton
_chat_redis_client = None  # Chatbot Redis singleton

def get_redis():
    """Returns the Market Redis client."""
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    url = os.getenv("UPSTASH_REDIS_URL")
    token = os.getenv("UPSTASH_REDIS_TOKEN")

    if not url or not token:
        print("[Redis] WARNING: UPSTASH_REDIS_URL or UPSTASH_REDIS_TOKEN not set. Market Redis disabled.")
        return None

    try:
        from upstash_redis import Redis
        _redis_client = Redis(url=url, token=token)
        _redis_client.ping()
        print("[Redis] Market Redis connected successfully.")
        return _redis_client
    except Exception as e:
        print(f"[Redis] WARNING: Could not connect to Market Redis — {e}. Disabled.")
        return None


def get_chat_redis():
    """Returns the dedicated Chatbot Redis client."""
    global _chat_redis_client

    if _chat_redis_client is not None:
        return _chat_redis_client

    url = os.getenv("CHAT_REDIS_URL")
    token = os.getenv("CHAT_REDIS_TOKEN")

    if not url or not token:
        print("[Redis] WARNING: CHAT_REDIS_URL or CHAT_REDIS_TOKEN not set. Chat Redis disabled.")
        return None

    try:
        from upstash_redis import Redis
        _chat_redis_client = Redis(url=url, token=token)
        _chat_redis_client.ping()
        print("[Redis] Chat Redis connected successfully.")
        return _chat_redis_client
    except Exception as e:
        print(f"[Redis] WARNING: Could not connect to Chat Redis — {e}. Disabled.")
        return None
