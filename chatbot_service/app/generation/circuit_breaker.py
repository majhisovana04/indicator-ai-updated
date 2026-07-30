# app/generation/circuit_breaker.py
import time


class CircuitBreaker:
    """
    Tracks whether a downstream service (Gemini) is known to be failing.
    Once tripped, skips calling it entirely until the cooldown expires —
    avoids wasting time on calls we already know will fail.
    """

    def __init__(self, cooldown_seconds: int = 300):  # 5 minutes
        self.cooldown_seconds = cooldown_seconds
        self.tripped_at = None

    def is_open(self) -> bool:
        """True = circuit is OPEN (blocking calls), False = safe to call."""
        if self.tripped_at is None:
            return False
        if time.time() - self.tripped_at > self.cooldown_seconds:
            self.tripped_at = None  # cooldown expired, reset
            return False
        return True

    def trip(self):
        self.tripped_at = time.time()