# app/generation/gemini_budget.py
import time
from datetime import datetime


class GeminiDailyBudget:
    """
    Tracks total Gemini calls made today across ALL users.
    Free tier allows only ~20 requests/day (see AI Studio dashboard) —
    this must be protected globally, not just per-user.
    """

    def __init__(self, daily_limit: int = 18):  # small buffer below the real 20
        self.daily_limit = daily_limit
        self.count = 0
        self.reset_date = datetime.now().date()

    def _check_reset(self):
        today = datetime.now().date()
        if today != self.reset_date:
            self.count = 0
            self.reset_date = today

    def can_call(self) -> bool:
        self._check_reset()
        return self.count < self.daily_limit

    def record_call(self):
        self._check_reset()
        self.count += 1