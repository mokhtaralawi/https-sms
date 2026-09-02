import time

from django.core.cache import cache
from django.conf import settings
from redis.exceptions import RedisError

logger = None
try:
    import logging
    logger = logging.getLogger("httpsms.ratelimit")
except Exception:  # pragma: no cover
    pass


class RateLimiter:
    """Redis-based sliding window rate limiter.

    Falls back to local in-memory counters if Redis is unavailable so the
    system remains functional (though not cluster-safe) during development.
    """

    def __init__(self, prefix: str = "ratelimit"):
        self.prefix = prefix

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple:
        """
        Record a hit and return (allowed, current_count, limit).
        Uses a fixed window for simplicity and correctness.
        """
        bucket = int(time.time() // window_seconds)
        redis_key = f"{self.prefix}:{bucket}:{key}"

        try:
            pipe = cache.client.get_client().pipeline()
            count = pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds + 5)
            count = count.execute()[0]
            return count <= limit, count, limit
        except (RedisError, AttributeError) as exc:
            if logger:
                logger.warning("Redis rate limiter unavailable, using memory: %s", exc)
            return self._memory_hit(redis_key, limit, window_seconds)

    def _memory_hit(self, key: str, limit: int, window_seconds: int) -> tuple:
        current = cache.get(key, 0)
        current += 1
        cache.set(key, current, timeout=window_seconds + 5)
        return current <= limit, current, limit

    def check_customer_limits(self, customer, rps_window: int = 1, per_min_window: int = 60,
                              per_hour_window: int = 3600, per_day_window: int = 86400,
                              per_month_window: int = 2592000):
        """
        Check all customer rate limits. Returns (allowed, exceeded_metric).
        """
        limits = customer.get_rate_limits()
        checks = {
            "requests_per_second": (self.hit(f"c:{customer.id}:rps", limits["rps"], rps_window), "requests_per_second"),
            "messages_per_minute": (self.hit(f"c:{customer.id}:min", limits["per_min"], per_min_window), "messages_per_minute"),
            "messages_per_hour": (self.hit(f"c:{customer.id}:hour", limits["per_hour"], per_hour_window), "messages_per_hour"),
            "messages_per_day": (self.hit(f"c:{customer.id}:day", limits["per_day"], per_day_window), "messages_per_day"),
            "messages_per_month": (self.hit(f"c:{customer.id}:month", limits["per_month"], per_month_window), "messages_per_month"),
        }
        for metric, ((allowed, count, limit), name) in checks.items():
            if not allowed:
                return False, name
        return True, None


rate_limiter = RateLimiter()
