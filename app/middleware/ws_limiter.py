"""Rate limiter pour WebSocket — limite les connexions par IP."""

import time

from app.logger import get_logger

logger = get_logger(__name__)


class WSRateLimiter:
    def __init__(self, max_per_minute: int = 10):
        self._max_per_minute = max_per_minute
        self._buckets: dict[str, list[float]] = {}
        self._last_cleanup = time.monotonic()

    def allow(self, client_ip: str) -> bool:
        now = time.monotonic()
        if now - self._last_cleanup > 60:
            self._cleanup(now)

        timestamps = self._buckets.setdefault(client_ip, [])
        cutoff = now - 60
        recent = [t for t in timestamps if t > cutoff]
        if len(recent) >= self._max_per_minute:
            logger.warning("ws_rate_limit_exceeded", client_ip=client_ip)
            return False
        recent.append(now)
        self._buckets[client_ip] = recent
        return True

    def _cleanup(self, now: float) -> None:
        cutoff = now - 120
        self._buckets = {ip: ts for ip, ts in self._buckets.items() if any(t > cutoff for t in ts)}
        self._last_cleanup = now


ws_rate_limiter = WSRateLimiter()
