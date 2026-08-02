"""
FastAPI dependency-injection wiring.

CHANGE LOG (v2.0): this file used to be the authentication seam — it held
`get_current_user`, `require_roles`, the OAuth2 bearer scheme and JWT decoding.
All of that is deleted: the platform has no accounts, so there is nothing to
authenticate and no roles to enforce. What remains is the genuinely
cross-cutting request concerns: rate limiting and shared query parameters.

The rate limiter is unchanged in *interface* but fixed in two real ways:
  1. Bug fix — the in-process dict grew without bound: an IP that made one
     request and never returned kept an entry forever, so a long-running process
     leaked memory proportional to the number of unique client IPs ever seen.
     Idle keys are now evicted during periodic sweeps.
  2. It raises a typed `RateLimitException` carrying a retry hint instead of a
     bare HTTPException, so clients can back off instead of hammering.
"""
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, Query, Request

from app.core.config import settings
from app.core.exceptions import RateLimitException
from app.domain.enums import Market

# --- Rate limiting -----------------------------------------------------------
# A sliding-window limiter keyed by client IP, held in process memory.
# Deliberately NOT Redis-backed here: the interface (a callable FastAPI
# dependency) is exactly what you swap for a Redis token-bucket without touching
# a single call site, and pretending to test a Redis limiter with no reachable
# Redis would be dishonest. For multi-replica deployments, swap the
# implementation — see docs/DEPLOYMENT.md.
_request_log: dict[str, deque[float]] = defaultdict(deque)
_last_sweep: float = 0.0
_SWEEP_INTERVAL_SECONDS = 300


def _sweep(now: float) -> None:
    """Evict IPs with no activity in the last window — bounds memory growth."""
    global _last_sweep
    if now - _last_sweep < _SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep = now
    cutoff = now - 60
    for ip in [ip for ip, hits in _request_log.items() if not hits or hits[-1] <= cutoff]:
        del _request_log[ip]


def rate_limiter(request: Request) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return

    now = time.time()
    _sweep(now)

    # X-Forwarded-For is set by NGINX in the containerized deployment; without
    # honouring it every request behind the proxy shares one bucket (the proxy's
    # IP) and a single noisy client rate-limits everyone.
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )

    window_start = now - 60
    hits = _request_log[client_ip]
    while hits and hits[0] <= window_start:
        hits.popleft()

    if len(hits) >= settings.RATE_LIMIT_PER_MINUTE:
        retry_after = max(1, int(60 - (now - hits[0])))
        raise RateLimitException(
            f"Rate limit of {settings.RATE_LIMIT_PER_MINUTE} requests/minute exceeded.",
            context={"retry_after_seconds": retry_after, "limit": settings.RATE_LIMIT_PER_MINUTE},
        )

    hits.append(now)


def reset_rate_limiter() -> None:
    """Test hook — clears all accumulated windows."""
    _request_log.clear()


# --- Shared query parameters -------------------------------------------------
def market_param(
    market: Market = Query(
        default=settings.DEFAULT_MARKET,
        description="Market to scope results to. `IN` = India (NSE), `US` = United States.",
    ),
) -> Market:
    return market


class Pagination:
    """
    Cursor-free offset pagination shared by every list endpoint.

    `limit` is hard-capped at 500 — an uncapped `limit` is a trivial
    denial-of-service vector (one request asking for a million rows can pin a
    worker and exhaust memory), and it was uncapped on several endpoints before.
    """

    def __init__(
        self,
        skip: int = Query(default=0, ge=0, le=1_000_000, description="Rows to skip."),
        limit: int = Query(default=100, ge=1, le=500, description="Max rows to return."),
    ) -> None:
        self.skip = skip
        self.limit = limit


MarketDep = Annotated[Market, Depends(market_param)]
PaginationDep = Annotated[Pagination, Depends(Pagination)]
