import redis
import os

# Get Redis configuration from environment variables or use defaults
REDIS_URL = os.getenv('REDIS_URL')  # e.g., "redis://localhost:6379/0" or "redis://redis:6379/0"
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))

# Create a connection pool for efficiency
if REDIS_URL:
    # Use Redis URL if provided (preferred for Docker Compose)
    redis_pool = redis.ConnectionPool.from_url(
        REDIS_URL,
        decode_responses=True
    )
else:
    # Fall back to individual parameters
    redis_pool = redis.ConnectionPool(
        host=REDIS_HOST, 
        port=REDIS_PORT, 
        db=REDIS_DB, 
        decode_responses=True
    )

def get_redis_connection():
    return redis.Redis(connection_pool=redis_pool)

# A single instance for your app to use
redis_conn = get_redis_connection()

# Define the order expiration time in seconds (5 minutes)
ORDER_EXPIRATION_SECONDS = 300
# Alias for backwards compatibility
CART_EXPIRATION_SECONDS = ORDER_EXPIRATION_SECONDS

# Test Redis connection
def test_redis_connection():
    """Test if Redis is accessible"""
    try:
        redis_conn.ping()
        return True
    except redis.ConnectionError:
        return False