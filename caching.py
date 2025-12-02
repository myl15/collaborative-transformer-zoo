"""
Redis-based caching layer for visualization results.
"""
import redis
import json
import hashlib
import logging
from functools import wraps
from typing import Optional, Callable, Any
import os

logger = logging.getLogger(__name__)

# Redis connection (using defaults, adjust for production)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()  # Test connection
    REDIS_AVAILABLE = True
    logger.info("Redis connected successfully")
except Exception as e:
    REDIS_AVAILABLE = False
    logger.warning(f"Redis unavailable: {e}. Caching disabled.")
    redis_client = None


def get_cache_key(model_name: str, text: str, view_type: str) -> str:
    """Generate a cache key from model parameters."""
    content = f"{model_name}:{text}:{view_type}"
    hash_val = hashlib.md5(content.encode()).hexdigest()
    return f"viz:{hash_val}"


def cache_viz_result(ttl_seconds: int = 3600):
    """Decorator to cache visualization results in Redis."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(model_name: str, text: str, view_type: str, *args, **kwargs) -> str:
            if not REDIS_AVAILABLE:
                # Bypass cache if Redis unavailable
                return func(model_name, text, view_type, *args, **kwargs)

            cache_key = get_cache_key(model_name, text, view_type)
            
            # Try to get from cache
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    logger.info(f"Cache HIT for {cache_key}")
                    return cached
            except Exception as e:
                logger.warning(f"Cache retrieval error: {e}")

            # Cache miss - compute result
            logger.info(f"Cache MISS for {cache_key}")
            result = func(model_name, text, view_type, *args, **kwargs)

            # Store in cache
            try:
                redis_client.setex(cache_key, ttl_seconds, result)
                logger.info(f"Cached result for {cache_key} (TTL: {ttl_seconds}s)")
            except Exception as e:
                logger.warning(f"Cache storage error: {e}")

            return result
        return wrapper
    return decorator


def get_cache_stats() -> dict:
    """Get Redis cache statistics."""
    if not REDIS_AVAILABLE or not redis_client:
        return {"available": False, "message": "Redis unavailable"}
    
    try:
        info = redis_client.info()
        keys_count = redis_client.dbsize()
        return {
            "available": True,
            "connected_clients": info.get("connected_clients", 0),
            "keys_in_cache": keys_count,
            "used_memory": info.get("used_memory_human", "N/A"),
            "evicted_keys": info.get("evicted_keys", 0),
        }
    except Exception as e:
        logger.error(f"Error fetching cache stats: {e}")
        return {"available": False, "error": str(e)}


def clear_cache():
    """Clear all cache (use with caution)."""
    if not REDIS_AVAILABLE or not redis_client:
        return False
    try:
        redis_client.flushdb()
        logger.info("Cache cleared")
        return True
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return False
