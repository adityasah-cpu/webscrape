# 🔴 Redis Cache Setup Guide

## Overview

Redis has been integrated into your Job Portal as a caching layer to improve performance. This guide explains setup and usage.

---

## Prerequisites

### 1. Install Redis

**Windows:**
- Download from: https://github.com/microsoftarchive/redis/releases
- Or use Windows Subsystem for Linux (WSL)
- Or use Docker: `docker run -d -p 6379:6379 redis`

**macOS:**
```bash
brew install redis
brew services start redis
```

**Linux (Ubuntu):**
```bash
sudo apt-get install redis-server
sudo systemctl start redis-server
```

### 2. Install Python Driver

```bash
pip install redis
```

✅ Already installed in your environment!

---

## Configuration

### Redis Connection Settings

Edit `redis_cache.py`:

```python
REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 0,
    'decode_responses': True,
    'socket_connect_timeout': 5,
    'socket_keepalive': True
}
```

**Defaults (no change needed):**
- Host: localhost
- Port: 6379
- Database: 0

---

## Verify Installation

### 1. Check Redis is Running

```bash
redis-cli ping
```

Expected output: `PONG`

### 2. Test API with Cache

```bash
# Fetch jobs (will cache results)
curl http://localhost:5000/api/jobs

# Check cache status
curl http://localhost:5000/api/cache-info
```

---

## What Gets Cached

### 1. Job Search Results
- Cache key: `jobs:kw:*:wt:*:c:*:jt:*`
- Expiry: 30 minutes
- Includes: search results with pagination

### 2. Statistics
- Cache key: `stats:all`
- Expiry: 30 minutes
- Includes: total jobs, by work type, by country, by source

### 3. Job Sources
- Cache key: `sources:list`
- Expiry: 24 hours
- Includes: available job sources

### 4. Job Count
- Cache key: `jobs:count`
- Expiry: 1 hour
- Includes: total number of jobs

---

## Cache Behavior

### Automatic Caching

When you:
- **Fetch jobs** → Results cached for 30 minutes
- **Get statistics** → Stats cached for 30 minutes
- **Fetch new jobs** → Cache automatically invalidated
- **Clear jobs** → Cache automatically cleared

### Response Headers

API responses include `"from_cache"` field:

```json
{
  "jobs": [...],
  "from_cache": true,  // If served from cache
  "total": 1243,
  "page": 1
}
```

---

## Cache Management Endpoints

### Get Cache Info

```bash
curl http://localhost:5000/api/cache-info
```

Response:
```json
{
  "cache": {
    "status": "connected",
    "keys": 25,
    "memory_used": "2.5M",
    "memory_peak": "5.2M"
  },
  "performance": {
    "hits": 150,
    "misses": 45,
    "hit_rate": "76.92%"
  }
}
```

### Clear Cache

```bash
curl -X DELETE http://localhost:5000/api/cache-clear
```

Response:
```json
{
  "success": true,
  "message": "Cache cleared successfully"
}
```

---

## Redis Commands

### Connect to Redis CLI

```bash
redis-cli
```

### Useful Commands

```redis
# Check connection
PING

# Get all keys
KEYS *

# Get specific key
GET jobs:kw:python:wt:all:c:all:jt:all:p:1:l:20

# Get memory info
INFO memory

# Get cache stats
INFO stats

# Flush cache
FLUSHDB

# Exit
EXIT
```

---

## Performance Benefits

### Before Cache (Database Only)
```
Request → PostgreSQL Query → Response
Time: 200-500ms
Database: Every request hits database
```

### After Cache (With Redis)
```
Request → Redis Lookup → Response (cached)
Time: 10-50ms (50x faster!)

Request → PostgreSQL Query → Redis Cache → Response (first time)
Time: 200-500ms (caches for 30 minutes)
```

### Hit Rate Impact

- **First request**: Cache miss, fetches from database
- **Subsequent requests (30 min window)**: Cache hit, instant response
- **After 30 min**: Cache expires, refreshes from database
- **After new jobs fetched**: Cache invalidated, updates

---

## Cache Strategies

### Popular Searches (Auto-cached)
```
- Python developer jobs
- Remote jobs in India
- Frontend developer positions
```

### Heavy Pages
- Page 1 (most users start here)
- Statistics dashboard
- Job sources list

### Invalidation
- After fetching new jobs
- When clearing jobs
- Manual cache clear via API

---

## Monitoring Cache

### Via API

```bash
# Check cache performance
curl http://localhost:5000/api/cache-info

# Expected: High hit rate (>70% for stable data)
```

### Via Redis CLI

```bash
redis-cli INFO stats
redis-cli INFO memory
redis-cli DBSIZE
```

### Via Python

```python
import redis_cache

# Get cache stats
redis_cache.monitor_cache()

# Get performance
perf = redis_cache.get_cache_performance()
print(f"Hit rate: {perf['hit_rate']}")
```

---

## Troubleshooting

### Redis Not Connected

**Error:** "Redis not available"

**Fix:**
1. Start Redis:
   ```bash
   # Windows
   redis-server

   # macOS
   brew services start redis

   # Linux
   sudo systemctl start redis-server
   ```

2. Check connection:
   ```bash
   redis-cli ping
   ```

### High Memory Usage

**Solution:**
1. Clear cache:
   ```bash
   curl -X DELETE http://localhost:5000/api/cache-clear
   ```

2. Reduce expiry times in `redis_cache.py`

3. Implement cache eviction policy in Redis config

### Slow Responses Despite Cache

**Possible causes:**
- Cache not initialized (check logs)
- Redis port blocked (check firewall)
- Cache expired (resets after expiry time)

**Solution:**
```bash
# Check Redis is running
redis-cli ping

# Flush and restart
redis-cli FLUSHDB
```

---

## Production Setup

### Performance Tuning

In Redis config file (`/etc/redis/redis.conf` or similar):

```conf
# Maximum memory (adjust to your needs)
maxmemory 256mb

# Eviction policy (remove oldest keys when full)
maxmemory-policy allkeys-lru

# Persistence (save to disk)
save 900 1
save 300 10
save 60 10000
```

### Monitoring Tools

1. **Redis Commander** (Web UI)
   ```bash
   npm install -g redis-commander
   redis-commander
   ```

2. **redis-stat** (Terminal Dashboard)
   ```bash
   gem install redis-stat
   redis-stat
   ```

3. **Grafana** (Production monitoring)
   - Integrates with Redis for dashboards

### Replication & High Availability

For production:
1. Setup Redis replication (master-slave)
2. Use Redis Sentinel for failover
3. Or use managed Redis (AWS ElastiCache, etc.)

---

## Docker Setup (Optional)

Run Redis in Docker:

```bash
# Run Redis container
docker run -d -p 6379:6379 --name job-portal-redis redis:latest

# Check running
docker ps

# Stop Redis
docker stop job-portal-redis
```

---

## Cache Invalidation Strategy

### Automatic Invalidation
- ✅ After fetching new jobs
- ✅ After clearing jobs
- ✅ After manual cache clear

### Manual Invalidation
```bash
# Via API
curl -X DELETE http://localhost:5000/api/cache-clear

# Via Redis CLI
redis-cli FLUSHDB
```

### Partial Invalidation
```python
import redis_cache

# Clear only job search cache
redis_cache.cache_clear_pattern("jobs:*")

# Clear only stats cache
redis_cache.cache_delete("stats:all")
```

---

## Performance Checklist

- [ ] Redis installed and running
- [ ] Python redis package installed
- [ ] Connection verified (redis-cli ping)
- [ ] API initialized cache on startup
- [ ] Cache endpoints working (/api/cache-info)
- [ ] Jobs endpoint returns from_cache field
- [ ] High cache hit rate (>50%)
- [ ] Memory usage acceptable

---

## Files Modified

- ✅ `api.py` - Added cache integration
- ✅ `redis_cache.py` - New cache module (created)

---

## Next Steps

1. Install Redis
2. Start Redis server
3. Restart Flask server: `python api.py`
4. Check cache info: `curl http://localhost:5000/api/cache-info`
5. Monitor hit rate and adjust settings

---

**Redis Setup Complete!** 🚀
