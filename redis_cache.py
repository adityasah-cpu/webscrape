"""
Redis Cache Module for Job Portal
Provides caching layer for improved performance
"""

import redis
import json
from datetime import datetime, timedelta

# Redis Connection Config
REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 0,
    'decode_responses': True,  # Auto-decode responses to strings
    'socket_connect_timeout': 5,
    'socket_keepalive': True
}

# Cache expiration times (in seconds)
CACHE_EXPIRY = {
    'jobs': 3600,           # 1 hour
    'stats': 1800,          # 30 minutes
    'sources': 86400,       # 24 hours
    'job_count': 3600,      # 1 hour
    'search': 1800,         # 30 minutes
}

# Global Redis client
redis_client = None


def init_cache():
    """Initialize Redis connection"""
    global redis_client
    try:
        redis_client = redis.Redis(**REDIS_CONFIG)
        # Test connection
        redis_client.ping()
        print("✓ Redis cache connected")
        return True
    except redis.ConnectionError as e:
        print(f"⚠️  Redis not available: {e}")
        print("   Continuing without cache...")
        redis_client = None
        return False
    except Exception as e:
        print(f"⚠️  Redis error: {e}")
        redis_client = None
        return False


def is_cache_available():
    """Check if Redis is available"""
    return redis_client is not None


def cache_get(key):
    """Get value from cache"""
    if not is_cache_available():
        return None

    try:
        value = redis_client.get(key)
        if value:
            return json.loads(value)
        return None
    except Exception as e:
        print(f"Cache get error for {key}: {e}")
        return None


def cache_set(key, value, expiry=None):
    """Set value in cache"""
    if not is_cache_available():
        return False

    try:
        json_value = json.dumps(value)

        if expiry:
            redis_client.setex(key, expiry, json_value)
        else:
            redis_client.set(key, json_value)

        return True
    except Exception as e:
        print(f"Cache set error for {key}: {e}")
        return False


def cache_delete(key):
    """Delete value from cache"""
    if not is_cache_available():
        return False

    try:
        redis_client.delete(key)
        return True
    except Exception as e:
        print(f"Cache delete error for {key}: {e}")
        return False


def cache_clear_pattern(pattern):
    """Clear cache by pattern (e.g., 'jobs:*')"""
    if not is_cache_available():
        return False

    try:
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
        return True
    except Exception as e:
        print(f"Cache clear pattern error for {pattern}: {e}")
        return False


def cache_clear_all():
    """Clear entire cache"""
    if not is_cache_available():
        return False

    try:
        redis_client.flushdb()
        print("✓ Cache cleared")
        return True
    except Exception as e:
        print(f"Cache clear error: {e}")
        return False


# ============ CACHE KEY GENERATORS ============

def get_jobs_cache_key(keyword="", work_type="", country="", job_type="", page=1, limit=20):
    """Generate cache key for job search"""
    key_parts = [
        "jobs",
        f"kw:{keyword}" if keyword else "kw:all",
        f"wt:{work_type}" if work_type else "wt:all",
        f"c:{country}" if country else "c:all",
        f"jt:{job_type}" if job_type else "jt:all",
        f"p:{page}:l:{limit}"
    ]
    return ":".join(key_parts)


def get_stats_cache_key():
    """Generate cache key for statistics"""
    return "stats:all"


def get_sources_cache_key():
    """Generate cache key for job sources"""
    return "sources:list"


def get_job_count_cache_key():
    """Generate cache key for job count"""
    return "jobs:count"


# ============ CACHE FUNCTIONS ============

def get_cached_jobs(keyword="", work_type="", country="", job_type="", page=1, limit=20):
    """Get jobs from cache"""
    key = get_jobs_cache_key(keyword, work_type, country, job_type, page, limit)
    return cache_get(key)


def set_cached_jobs(jobs_data, keyword="", work_type="", country="", job_type="", page=1, limit=20):
    """Cache jobs search results"""
    key = get_jobs_cache_key(keyword, work_type, country, job_type, page, limit)
    cache_set(key, jobs_data, CACHE_EXPIRY['search'])
    return True


def get_cached_stats():
    """Get statistics from cache"""
    key = get_stats_cache_key()
    return cache_get(key)


def set_cached_stats(stats_data):
    """Cache statistics"""
    key = get_stats_cache_key()
    cache_set(key, stats_data, CACHE_EXPIRY['stats'])
    return True


def invalidate_job_cache():
    """Invalidate all job-related cache"""
    if not is_cache_available():
        return False

    try:
        # Clear all job search caches
        cache_clear_pattern("jobs:*")
        # Clear stats cache
        cache_delete(get_stats_cache_key())
        # Clear job count cache
        cache_delete(get_job_count_cache_key())
        print("✓ Job cache invalidated")
        return True
    except Exception as e:
        print(f"Cache invalidation error: {e}")
        return False


def get_cached_job_count():
    """Get job count from cache"""
    key = get_job_count_cache_key()
    count = cache_get(key)
    return count


def set_cached_job_count(count):
    """Cache job count"""
    key = get_job_count_cache_key()
    cache_set(key, count, CACHE_EXPIRY['job_count'])
    return True


def get_cached_sources():
    """Get sources from cache"""
    key = get_sources_cache_key()
    return cache_get(key)


def set_cached_sources(sources_data):
    """Cache sources"""
    key = get_sources_cache_key()
    cache_set(key, sources_data, CACHE_EXPIRY['sources'])
    return True


# ============ CACHE STATISTICS ============

def get_cache_info():
    """Get Redis cache information"""
    if not is_cache_available():
        return {
            "status": "unavailable",
            "message": "Redis not connected"
        }

    try:
        info = redis_client.info()
        keys = redis_client.dbsize()

        return {
            "status": "connected",
            "keys": keys,
            "memory_used": info.get('used_memory_human', 'N/A'),
            "memory_peak": info.get('used_memory_peak_human', 'N/A'),
            "evicted_keys": info.get('evicted_keys', 0),
            "keyspace_hits": info.get('keyspace_hits', 0),
            "keyspace_misses": info.get('keyspace_misses', 0),
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def get_cache_performance():
    """Get cache hit/miss statistics"""
    if not is_cache_available():
        return None

    try:
        info = redis_client.info()
        hits = info.get('keyspace_hits', 0)
        misses = info.get('keyspace_misses', 0)
        total = hits + misses

        if total == 0:
            hit_rate = 0
        else:
            hit_rate = (hits / total) * 100

        return {
            "hits": hits,
            "misses": misses,
            "total": total,
            "hit_rate": f"{hit_rate:.2f}%"
        }
    except Exception as e:
        print(f"Error getting cache performance: {e}")
        return None


# ============ CACHE WARMING ============

def warm_cache(jobs_data, stats_data, sources_data):
    """Pre-load cache with important data"""
    if not is_cache_available():
        return False

    try:
        count = 0

        # Cache statistics
        if stats_data:
            set_cached_stats(stats_data)
            count += 1

        # Cache sources
        if sources_data:
            set_cached_sources(sources_data)
            count += 1

        # Cache popular pages of jobs
        if jobs_data:
            for page in range(1, 4):  # Cache first 3 pages
                set_cached_jobs(
                    {
                        "jobs": jobs_data.get("jobs", []),
                        "total": jobs_data.get("total", 0),
                        "page": page,
                        "pages": jobs_data.get("pages", 0)
                    }
                )
                count += 1

        print(f"✓ Cache warmed with {count} items")
        return True
    except Exception as e:
        print(f"Cache warming error: {e}")
        return False


# ============ CACHE MONITORING ============

def monitor_cache():
    """Print cache statistics"""
    if not is_cache_available():
        print("Redis is not available")
        return

    try:
        print("\n" + "=" * 60)
        print("📊 REDIS CACHE STATISTICS")
        print("=" * 60)

        info = get_cache_info()
        print(f"\nStatus: {info.get('status', 'unknown')}")
        print(f"Keys Stored: {info.get('keys', 0)}")
        print(f"Memory Used: {info.get('memory_used', 'N/A')}")
        print(f"Memory Peak: {info.get('memory_peak', 'N/A')}")

        perf = get_cache_performance()
        if perf:
            print(f"\nCache Performance:")
            print(f"  Hits: {perf['hits']}")
            print(f"  Misses: {perf['misses']}")
            print(f"  Hit Rate: {perf['hit_rate']}")

        print("=" * 60 + "\n")
    except Exception as e:
        print(f"Monitoring error: {e}")
