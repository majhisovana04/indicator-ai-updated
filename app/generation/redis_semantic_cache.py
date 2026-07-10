# app/generation/redis_semantic_cache.py
"""
Redis-backed semantic cache — tagged by answer type.

Two independent caches:
    - "education"  : TTL 7 days  — indicator explanations, very stable
    - "market"     : TTL 6 hours — live market summaries, expire naturally

Storage: One Redis Hash per type (one hgetall = all candidates in a single call).
Lookup : Cosine similarity in Python against all stored embeddings of that type.
Fallback: If Redis is down, returns None (miss) — falls through to LLM.
"""

import json
import uuid
import numpy as np
from datetime import datetime
from app.redis_client import get_redis


class RedisSemanticCache:

    EDUCATION = "education"
    MARKET = "market"

    TTL_EDUCATION = 7 * 24 * 3600   # 7 days
    TTL_MARKET    = 6 * 3600        # 6 hours — hard expire, never extended

    MAX_ENTRIES = 300   # FIFO cap per type to keep hash size bounded

    def __init__(self, embedder, similarity_threshold: float = 0.82):
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold

    # ── Internal helpers ──────────────────────────────────────────

    def _hash_key(self, cache_type: str) -> str:
        return f"scache:{cache_type}"

    def _cosine_similarity(self, a: list, b: list) -> float:
        va, vb = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
        norm = np.linalg.norm(va) * np.linalg.norm(vb)
        return float(np.dot(va, vb) / norm) if norm > 0 else 0.0

    # ── Public API ────────────────────────────────────────────────

    def get(self, query: str, cache_type: str = EDUCATION) -> str | None:
        """
        Returns a cached answer if a semantically similar query was seen before.
        Searches ONLY within the given cache_type — no cross-type contamination.
        Returns None on miss or Redis unavailability.
        """
        r = get_redis()
        if r is None:
            return None

        try:
            query_embedding = self.embedder.embed_query(query)[0].tolist()
            raw_entries = r.hgetall(self._hash_key(cache_type))

            if not raw_entries:
                return None

            best_score = 0.0
            best_answer = None

            for _, entry_json in raw_entries.items():
                entry = json.loads(entry_json)
                score = self._cosine_similarity(query_embedding, entry["embedding"])
                if score > best_score:
                    best_score = score
                    best_answer = entry["answer"]

            if best_score >= self.similarity_threshold:
                print(f"[RedisSemanticCache] {cache_type} HIT (similarity={best_score:.3f})")
                return best_answer

            return None

        except Exception as e:
            print(f"[RedisSemanticCache] get error ({cache_type}): {e}")
            return None

    def set(self, query: str, answer: str, cache_type: str = EDUCATION):
        """
        Stores a query→answer pair with its embedding.
        Education: TTL extended on every write (stable data).
        Market: TTL set ONLY on first write (must expire naturally).
        """
        r = get_redis()
        if r is None:
            return

        try:
            embedding = self.embedder.embed_query(query)[0].tolist()
            entry_id = str(uuid.uuid4())
            entry = {
                "embedding": embedding,
                "answer": answer,
                "query": query,
                "created_at": datetime.now().isoformat(),
                "cache_type": cache_type,
            }

            hash_key = self._hash_key(cache_type)

            r.hset(hash_key, entry_id, json.dumps(entry))

            # TTL strategy differs by type
            if cache_type == self.MARKET:
                # Only set TTL on first write — let market data expire naturally
                existing_ttl = r.ttl(hash_key)
                if existing_ttl <= 0:
                    r.expire(hash_key, self.TTL_MARKET)
            else:
                # Education: always refresh TTL (indicator definitions are stable)
                r.expire(hash_key, self.TTL_EDUCATION)

            # FIFO eviction: if over cap, remove oldest entry
            all_entries = r.hgetall(hash_key)
            if len(all_entries) > self.MAX_ENTRIES:
                oldest_id = next(iter(all_entries))
                r.hdel(hash_key, oldest_id)

        except Exception as e:
            print(f"[RedisSemanticCache] set error ({cache_type}): {e}")
