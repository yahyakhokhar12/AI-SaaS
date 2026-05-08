import os
from datetime import datetime, timezone
from typing import Dict

from dotenv import load_dotenv
import redis

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "40"))
PRO_DAILY_LIMIT = int(os.getenv("PRO_DAILY_LIMIT", "400"))

_memory_counter: Dict[str, int] = {}


def _utc_day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _redis_client():
    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def _daily_limit_for_plan(plan: str) -> int:
    return PRO_DAILY_LIMIT if plan == "pro" else FREE_DAILY_LIMIT


def check_and_consume_user_request(user_id: int, plan: str) -> tuple[bool, int]:
    limit = _daily_limit_for_plan(plan)
    key = f"usage:{user_id}:{_utc_day_key()}"

    client = _redis_client()
    if client:
        count = client.incr(key)
        if count == 1:
            client.expire(key, 60 * 60 * 24)
        remaining = max(0, limit - count)
        return count <= limit, remaining

    count = _memory_counter.get(key, 0) + 1
    _memory_counter[key] = count
    remaining = max(0, limit - count)
    return count <= limit, remaining
