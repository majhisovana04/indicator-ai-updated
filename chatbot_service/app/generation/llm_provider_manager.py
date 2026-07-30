# app/generation/llm_provider_manager.py
"""
LLM Provider Manager — multi-provider fallback chain.

Priority Order:
    1. Gemini      (google-genai SDK)
    2. Groq        (groq SDK — OpenAI-compatible)
    3. OpenRouter  (HTTP — OpenAI-compatible, free models)
    4. Cerebras    (HTTP — OpenAI-compatible)

Each provider has its own:
    - CircuitBreaker  (trips on 5xx/network errors, cools down in 5 min)
    - DailyBudget     (tracks calls today, resets at midnight)

On any failure → next provider is tried automatically.
All providers exhausted → raises ProviderExhausted.
"""

import os
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from chatbot_service.app.generation.redis_provider_budget import RedisProviderBudget
load_dotenv()


# ─────────────────────────────────────────────────────────────────
# Per-Provider Circuit Breaker
# ─────────────────────────────────────────────────────────────────

class ProviderCircuitBreaker:
    """
    Tracks failure state for a single LLM provider.
    Once tripped, blocks calls to that provider until cooldown expires.
    """
    def __init__(self, provider_name: str, cooldown_seconds: int = 300):
        self.provider_name = provider_name
        self.cooldown_seconds = cooldown_seconds
        self.tripped_at: float | None = None

    def is_open(self) -> bool:
        """True = circuit is OPEN (skip this provider). False = safe to call."""
        if self.tripped_at is None:
            return False
        if time.time() - self.tripped_at > self.cooldown_seconds:
            self.tripped_at = None  # cooldown expired — auto-reset
            return False
        return True

    def trip(self):
        """Trip the circuit — block this provider for cooldown_seconds."""
        self.tripped_at = time.time()

    def reset(self):
        """Manually reset circuit after a successful call."""
        self.tripped_at = None



# ─────────────────────────────────────────────────────────────────
# Provider 1 — Gemini
# ─────────────────────────────────────────────────────────────────

class GeminiProvider:
    NAME = "Gemini"

    def __init__(self):
        from google import genai
        from google.genai import errors as genai_errors
        self._errors = genai_errors
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = "gemini-flash-latest"
        self.circuit_breaker = ProviderCircuitBreaker(self.NAME)
        self.budget = RedisProviderBudget(self.NAME, daily_limit=18)  # buffer below real 20

    def generate(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model, contents=prompt
        )
        return response.text.strip()

    def is_quota_error(self, exc: Exception) -> bool:
        """429 / ClientError → quota hit, exhaust budget."""
        return isinstance(exc, self._errors.ClientError)

    def is_server_error(self, exc: Exception) -> bool:
        """503 / ServerError → temporary, trip circuit."""
        return isinstance(exc, self._errors.ServerError)


# ─────────────────────────────────────────────────────────────────
# Provider 2 — Groq
# ─────────────────────────────────────────────────────────────────

class GroqProvider:
    NAME = "Groq"

    def __init__(self):
        from groq import Groq, APIStatusError
        self._APIStatusError = APIStatusError
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "openai/gpt-oss-20b"  # free-tier Groq model
        self.circuit_breaker = ProviderCircuitBreaker(self.NAME)
        self.budget = RedisProviderBudget(self.NAME, daily_limit=14400)  # Groq free: 14400/day

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        return response.choices[0].message.content.strip()

    def is_quota_error(self, exc: Exception) -> bool:
        return isinstance(exc, self._APIStatusError) and exc.status_code == 429

    def is_server_error(self, exc: Exception) -> bool:
        return isinstance(exc, self._APIStatusError) and exc.status_code >= 500


# ─────────────────────────────────────────────────────────────────
# Provider 3 — OpenRouter
# ─────────────────────────────────────────────────────────────────

class OpenRouterProvider:
    NAME = "OpenRouter"
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = "openrouter/free"   # free model on OpenRouter
        self.circuit_breaker = ProviderCircuitBreaker(self.NAME)
        self.budget = RedisProviderBudget(self.NAME, daily_limit=200)

    def generate(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://xanefunds.com",   # required by OpenRouter policy
        }
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        }
        response = requests.post(self.BASE_URL, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    def is_quota_error(self, exc: Exception) -> bool:
        return isinstance(exc, requests.HTTPError) and exc.response.status_code == 429

    def is_server_error(self, exc: Exception) -> bool:
        return (
            isinstance(exc, (requests.ConnectionError, requests.Timeout))
            or (isinstance(exc, requests.HTTPError) and exc.response.status_code >= 500)
        )


# ─────────────────────────────────────────────────────────────────
# Provider 4 — Cerebras
# ─────────────────────────────────────────────────────────────────

class CerebrasProvider:
    NAME = "Cerebras"
    BASE_URL = "https://api.cerebras.ai/v1/chat/completions"

    def __init__(self):
        self.api_key = os.getenv("CEREBRAS_API_KEY")
        self.model = "gpt-oss-120b"
        self.circuit_breaker = ProviderCircuitBreaker(self.NAME)
        self.budget = RedisProviderBudget(self.NAME, daily_limit=60)

    def generate(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        }
        response = requests.post(self.BASE_URL, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    def is_quota_error(self, exc: Exception) -> bool:
        return isinstance(exc, requests.HTTPError) and exc.response.status_code == 429

    def is_server_error(self, exc: Exception) -> bool:
        return (
            isinstance(exc, (requests.ConnectionError, requests.Timeout))
            or (isinstance(exc, requests.HTTPError) and exc.response.status_code >= 500)
        )


# ─────────────────────────────────────────────────────────────────
# ProviderExhausted — raised when ALL providers fail
# ─────────────────────────────────────────────────────────────────

class ProviderExhausted(Exception):
    """
    Raised when every LLM provider in the fallback chain has been tried
    and all have failed — either due to quota limits, server errors, or
    circuit breakers being open.
    """
    pass


# ─────────────────────────────────────────────────────────────────
# The Manager — Orchestrates the Full Fallback Chain
# ─────────────────────────────────────────────────────────────────

class LLMProviderManager:
    """
    Tries each LLM provider in priority order:
        Gemini → Groq → OpenRouter → Cerebras → TogetherAI

    A provider is SKIPPED if:
        - Its circuit breaker is OPEN  (recently had server errors)
        - Its daily budget is EXHAUSTED (quota limit hit today)

    On any error:
        - Quota error (429)  → budget.exhaust(), move to next
        - Server error (5xx) → circuit_breaker.trip(), move to next
        - Unknown error      → circuit_breaker.trip(), move to next

    On success:
        - circuit_breaker.reset() on the winning provider
        - Returns the generated text string

    All providers failed:
        - Raises ProviderExhausted with a professional message
    """

    def __init__(self):
        self.providers = [
            GeminiProvider(),
            GroqProvider(),
            OpenRouterProvider(),
            CerebrasProvider(),

        ]

    def generate(self, prompt: str) -> str:
        failed_providers: list[str] = []
        last_error: Exception | None = None

        for provider in self.providers:
            name = provider.NAME

            # --- Guard 1: Circuit breaker ---
            if provider.circuit_breaker.is_open():
                print(f"[LLMProviderManager] {name}: circuit is open — skipping.")
                failed_providers.append(f"{name} (circuit open)")
                continue

            # --- Guard 2: Daily budget ---
            if not provider.budget.can_call():
                print(f"[LLMProviderManager] {name}: daily budget exhausted — skipping.")
                failed_providers.append(f"{name} (budget exhausted)")
                continue

            # --- Attempt call ---
            try:
                print(
                    f"[LLMProviderManager] Attempting {name} "
                    f"(budget remaining: {provider.budget.remaining()})..."
                )
                provider.budget.record_call()
                result = provider.generate(prompt)
                provider.circuit_breaker.reset()
                print(f"[LLMProviderManager] {name}: responded successfully ")
                return result

            except Exception as exc:
                last_error = exc

                if provider.is_quota_error(exc):
                    print(f"[LLMProviderManager] {name}: quota limit reached — exhausting budget.")
                    provider.budget.exhaust()
                    failed_providers.append(f"{name} (quota exceeded)")

                elif provider.is_server_error(exc):
                    print(f"[LLMProviderManager] {name}: server/network error — tripping circuit breaker.")
                    provider.circuit_breaker.trip()
                    failed_providers.append(f"{name} (server error)")

                else:
                    print(f"[LLMProviderManager] {name}: unexpected error — tripping circuit breaker. Error: {exc}")
                    provider.circuit_breaker.trip()
                    failed_providers.append(f"{name} (unexpected error)")

                print(f"[LLMProviderManager] Falling back to next provider...")

        # All providers tried and none succeeded
        tried_str = ", ".join(failed_providers) if failed_providers else "none were available"
        raise ProviderExhausted(
            "The AI assistant is temporarily unavailable. "
            "Our system automatically attempted multiple language model providers "
            f"({tried_str}), and all are currently unreachable or have reached their "
            "daily capacity. This is a temporary condition — please try again in a few minutes."
        )

    def status(self) -> dict:
        """
        Returns a snapshot of all provider states.
        Useful for exposing in the /health API endpoint.
        """
        return {
            p.NAME: {
                "circuit_open": p.circuit_breaker.is_open(),
                "budget_remaining": p.budget.remaining(),
            }
            for p in self.providers
        }
