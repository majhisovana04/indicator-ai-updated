
# app/pipeline.py
from chatbot_service.app.embedding.embedder import Embedder
from chatbot_service.app.vectorstore.vector_store import VectorStore
from chatbot_service.app.routing.router import Router, Route
from chatbot_service.app.generation.response_executor import ResponseExecutor
from chatbot_service.app.generation.redis_semantic_cache import RedisSemanticCache
from chatbot_service.app.routing.query_classifier import QueryClassifier, QueryIntent
from chatbot_service.app.routing.company_detector import CompanyDetector
from market_service.app.market.screener import Screener
from core_shared.redis_client import get_redis
import json
import time


import psutil, os, sys

def _mem(label):
    rss = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    print(f"[MEM] {label}: {rss:.1f} MB", flush=True)

class AssistantPipeline:
    def __init__(self):
        _mem("start")
        
        self.embedder = Embedder()
        _mem("after Embedder()")
        
        self.store = VectorStore()
        _mem("after VectorStore() created")
        
        self.store.load()
        _mem("after VectorStore.load()")
        
        self.router = Router()
        _mem("after Router()")
        
        self.executor = ResponseExecutor(embedder=self.embedder)
        _mem("after ResponseExecutor()")
        
        self.query_classifier = QueryClassifier(embedder=self.embedder)
        _mem("after QueryClassifier()")
        
        self.company_detector = CompanyDetector(index="nifty500")
        _mem("after CompanyDetector()")
        
        self.screener = Screener()
        _mem("end of __init__")

    def _describe_company_sentiment(self, company_symbol: str) -> str:
        """
        Used ONLY for the SAFETY branch — describes what indicators
        show WITHOUT a buy/sell verdict. Reuses the same signals
        Screener.analyze_specific_company() already computes.
        """
        full_symbol = f"NSE:{company_symbol}"
        try:
            analysis = self.screener.analyze_specific_company(full_symbol)
            if not analysis["available"]:
                return (
                    f"I can't tell you whether to buy or sell — that's a decision only you "
                    f"(or a registered advisor) should make. I also can't provide reliable "
                    f"technical signals for {company_symbol} right now: {analysis['reason']}"
                )

            bullish_count = sum(1 for s in analysis["signals"] if "bullish" in s.lower() or "above" in s.lower() or "recovering" in s.lower())
            if bullish_count >= 2:
                sentiment = "bullish"
            elif bullish_count == 0:
                sentiment = "bearish"
            else:
                sentiment = "neutral"

            return (
                f"I can't tell you whether to buy or sell — that's a decision only you "
                f"(or a registered advisor) should make. What I can tell you is that "
                f"technical indicators currently show {company_symbol} as {sentiment}. "
                f"This reflects technical signals only, not investment advice."
            )
        except Exception as e:
            print(f"[Pipeline] SAFETY company sentiment lookup failed for {full_symbol}: {e}")
            return (
                "I can't tell you whether to buy or sell or any future prediction  — that's a decision only you "
                "(or a registered advisor) should make. I can explain what technical "
                "indicators suggest and how traders interpret them."
            )

    def _get_company_signal(self, full_symbol: str) -> tuple[str, str]:
        """
        EXACT-KEY cache for company-specific signals — NOT the fuzzy
        semantic cache. Company identity must never be "fuzzy matched":
        two differently-worded questions about two DIFFERENT companies
        could otherwise embed closely enough to cross-contaminate
        (e.g. "signal for X?" vs "signal for Y?" scoring high on pure
        sentence-shape similarity). Keying by the real ticker makes
        that impossible by construction, regardless of phrasing.

        Returns (answer, tier).
        """
        r = get_redis()
        cache_key = f"company_signal:{full_symbol}"

        cached = r.get(cache_key) if r else None
        if cached:
            return json.loads(cached)["answer"], "company_cached"

        try:
            analysis = self.screener.analyze_specific_company(full_symbol)
            if analysis["available"]:
                signals_text = ", ".join(analysis["signals"])
                answer = (
                    f"For {full_symbol}: {signals_text}. "
                    f"This reflects technical indicator signals, not investment advice."
                )
            else:
                answer = (
                    f"I can share {full_symbol}'s current price, but I can't provide "
                    f"reliable technical analysis for it right now: {analysis['reason']}"
                )

            if r:
                # 1h TTL — deliberately short since this is live-ish data,
                # not stable education content.
                r.set(cache_key, json.dumps({"answer": answer}), ex=3600)

            return answer, "company_specific"

        except Exception as e:
            print(f"[Pipeline] company-specific analysis failed for {full_symbol}: {e}")
            return (
                f"I couldn't fetch live data for {full_symbol} right now. Please try again shortly.",
                "company_specific_failed"
            )

    def ask(self, query: str, top_k: int = 3) -> dict:
        t0 = time.time()

        # Step 0: Embed ONCE
        query_embedding = self.embedder.embed_query(query)
        query_vec_1d = query_embedding[0].tolist()

        # Step 1: FAISS search ONCE — reused by SAFETY fallback extraction AND education routing
        faiss_results = self.store.search(query_embedding, top_k=top_k)

        # Step 2: Classify ONCE — argmax across SAFETY / LIVE_SCREENING / EDUCATION / OFF_TOPIC
        t1 = time.time()
        intent, scores = self.query_classifier.classify_with_vec(query_vec_1d)
        t2 = time.time()
        print(f"Query classification: {t2-t1:.3f}s -> {intent.value} | {scores}")

        # ── Branch 1: SAFETY ──────────────────────────────────────
        if intent == QueryIntent.SAFETY:
            company_symbol = self.company_detector.find_company(query)

            if company_symbol:
                answer = self._describe_company_sentiment(company_symbol)
                return {
                    "answer": answer,
                    "tier": "policy_direct",
                    "source": None,
                    "distance": None
                }

            policy_route = self.router.decide(faiss_results)
            if policy_route == Route.POLICY:
                top_chunk = faiss_results[0]["chunk"]
                return {
                    "answer": self.executor.extractor.extract_answer(top_chunk),
                    "tier": "policy_direct",
                    "source": top_chunk.source,
                    "distance": faiss_results[0]["distance"]
                }
            return {
                "answer": "I can't offer guarantees about future price movements or tell you what to trade or give you accurate prediction about any stock or index — no one honestly can. What I can do is walk you through what the technical indicators are showing right now, so you have real information to work with. Want me to explain a specific indicator, or check the signals for a particular stock?",
                "tier": "policy_direct",
                "source": None,
                "distance": None
            }

        # ── Branch 2: LIVE_SCREENING ──────────────────────────────
        if intent == QueryIntent.LIVE_SCREENING:
            company_symbol = self.company_detector.find_company(query)

            if company_symbol:
                full_symbol = f"NSE:{company_symbol}"
                answer, tier = self._get_company_signal(full_symbol)
                return {"answer": answer, "tier": tier, "distance": None}

            # No company named — general market summary (safe to stay
            # on the fuzzy semantic cache, since there's only ONE true
            # "today's market" answer regardless of how it's phrased)
            cached = self.executor.semantic_cache.get(
                query, cache_type=RedisSemanticCache.MARKET, query_vector=query_vec_1d
            )
            if cached:
                return {"answer": cached, "tier": "market_cached", "distance": None}

            r = get_redis()
            cached_market_json = r.get("market:daily_summary") if r else None
            if cached_market_json:
                cached_market = json.loads(cached_market_json)
                answer = cached_market["answer"]
                self.executor.semantic_cache.set(
                    query, answer, cache_type=RedisSemanticCache.MARKET, query_vector=query_vec_1d
                )
                return {"answer": answer, "tier": "live_screening", "distance": None}

            return {
                "answer": "Today's market analysis is still being prepared — it updates once daily shortly after market close (around 3:30 PM IST). Check back then for a fresh look at today's technical signals. In the meantime, I'm happy to explain how any of the indicators work.",
                "tier": "live_screening_pending",
                "distance": None
            }

        # ── Branch 3: EDUCATION (default) + OFF_TOPIC ─────────────
        cached = self.executor.semantic_cache.get(
            query, cache_type=RedisSemanticCache.EDUCATION, query_vector=query_vec_1d
        )
        if cached:
            return {"answer": cached, "tier": "llm_cached", "distance": None}

        route = self.router.decide(faiss_results)
        return self.executor.execute(route, query, faiss_results, query_vector=query_vec_1d)