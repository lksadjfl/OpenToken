import time
from collections import defaultdict
from typing import Any

import redis

from .config import REDIS_URL


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, tuple[Any, float | None]] = {}
        self.counters: dict[str, tuple[int, float | None]] = {}
        self.sets: dict[str, set[str]] = defaultdict(set)

    def _expired(self, expires_at: float | None) -> bool:
        return expires_at is not None and time.time() > expires_at

    def get(self, key: str) -> Any:
        item = self.values.get(key)
        if not item or self._expired(item[1]):
            self.values.pop(key, None)
            return None
        return item[0]

    def setex(self, key: str, ttl: int, value: Any) -> None:
        self.values[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.counters.pop(key, None)

    def incr(self, key: str) -> int:
        value, expires_at = self.counters.get(key, (0, None))
        if self._expired(expires_at):
            value, expires_at = 0, None
        value += 1
        self.counters[key] = (value, expires_at)
        return value

    def expire(self, key: str, ttl: int) -> None:
        value, _ = self.counters.get(key, (0, None))
        self.counters[key] = (value, time.time() + ttl)

    def scard(self, key: str) -> int:
        return len(self.sets[key])

    def sadd(self, key: str, value: str) -> None:
        self.sets[key].add(value)

    def srem(self, key: str, value: str) -> None:
        self.sets[key].discard(value)

    def ping(self) -> bool:
        return True


_client: Any | None = None


def redis_client() -> Any:
    global _client
    if _client is not None:
        return _client
    if REDIS_URL == "memory://":
        _client = MemoryRedis()
    else:
        _client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _client.ping()
    return _client
