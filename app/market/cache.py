import time


class SimpleCache:
    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self.cached_result = None
        self.cached_at = None

    def get(self):
        if self.cached_result is None:
            return None
        if time.time() - self.cached_at > self.ttl_seconds:
            return None
        return self.cached_result

    def set(self, result):
        self.cached_result = result
        self.cached_at = time.time()