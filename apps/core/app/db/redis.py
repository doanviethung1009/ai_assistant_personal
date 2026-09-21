from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis, from_url

from app.core.config import settings


@lru_cache
def get_redis() -> Redis:
    return from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        health_check_interval=30,
    )


async def close_redis() -> None:
    client = get_redis()
    await client.aclose()
    get_redis.cache_clear()
