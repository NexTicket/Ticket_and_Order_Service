#!/usr/bin/env python3
"""
Test script for Redis connection and basic operations
Tests connection, basic operations, expiration, and cart-like operations
"""

import sys
import os
import time
import json
from datetime import datetime, timezone, timedelta

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Database.redis_client import test_redis_connection, redis_conn, CART_EXPIRATION_SECONDS

def print_separator(title):
    """Print a nice separator for test sections"""
    print(f"\n{'='*50}")
    print(f" {title}")
    print(f"{'='*50}")

def test_basic_connection():
    """Test basic Redis connection"""
    print_separator("Testing Redis Connection")
    
    if test_redis_connection():
        print("✅ Redis connection successful!")
        return True
    else:
        print("❌ Redis connection failed!")
        print("Make sure Redis server is running:")
        print("  - Linux/Mac: redis-server")
        print("  - Windows: Start Redis service")
        print("  - Docker: docker run -d -p 6379:6379 redis:alpine")
        return False

def test_basic_operations():
    """Test basic Redis set/get operations"""
    print_separator("Testing Basic Operations")
    
    try:
        # Test string operations
        test_key = "test:basic_string"
        test_value = "Hello Redis!"
        
        redis_conn.set(test_key, test_value)
        retrieved_value = redis_conn.get(test_key)
        
        if retrieved_value == test_value:
            print(f"✅ String operation successful: {retrieved_value}")
        else:
            print(f"❌ String operation failed: expected '{test_value}', got '{retrieved_value}'")
            return False
        
        # Test number operations
        counter_key = "test:counter"
        redis_conn.set(counter_key, 0)
        redis_conn.incr(counter_key)
        redis_conn.incr(counter_key, 5)
        counter_value = int(redis_conn.get(counter_key))
        
        if counter_value == 6:
            print(f"✅ Counter operation successful: {counter_value}")
        else:
            print(f"❌ Counter operation failed: expected 6, got {counter_value}")
            return False
        
        # Cleanup
        redis_conn.delete(test_key, counter_key)
        print("✅ Basic operations cleanup completed")
        return True
        
    except Exception as e:
        print(f"❌ Basic operations failed: {e}")
        return False

def test_expiration():
    """Test Redis key expiration"""
    print_separator("Testing Expiration")
    
    try:
        # Test with short expiration for quick testing
        expire_key = "test:expire_key"
        expire_value = "This will expire"
        expire_seconds = 3
        
        # Set key with expiration
        redis_conn.setex(expire_key, expire_seconds, expire_value)
        
        # Check initial value and TTL
        initial_value = redis_conn.get(expire_key)
        initial_ttl = redis_conn.ttl(expire_key)
        
        print(f"✅ Key set with value: '{initial_value}', TTL: {initial_ttl} seconds")
        
        # Wait and check again
        print(f"⏳ Waiting {expire_seconds + 1} seconds for expiration...")
        time.sleep(expire_seconds + 1)
        
        expired_value = redis_conn.get(expire_key)
        if expired_value is None:
            print("✅ Key expired successfully")
            return True
        else:
            print(f"❌ Key should have expired but still has value: '{expired_value}'")
            return False
            
    except Exception as e:
        print(f"❌ Expiration test failed: {e}")
        return False

def test_hash_operations():
    """Test Redis hash operations (used for cart data)"""
    print_separator("Testing Hash Operations")
    
    try:
        hash_key = "test:user_cart"
        cart_data = {
            "cart_id": "test-cart-123",
            "user_id": "test-user-456",
            "event_id": "1",
            "seat_ids": json.dumps(["A1", "A2", "A3"]),
            "status": "locked",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=CART_EXPIRATION_SECONDS)).isoformat()
        }
        
        # Set hash data
        redis_conn.hset(hash_key, mapping=cart_data)
        redis_conn.expire(hash_key, CART_EXPIRATION_SECONDS)
        
        # Retrieve hash data
        retrieved_data = redis_conn.hgetall(hash_key)
        
        if retrieved_data:
            print("✅ Cart data stored successfully:")
            for key, value in retrieved_data.items():
                print(f"   {key}: {value}")
            
            # Test individual field retrieval
            user_id = redis_conn.hget(hash_key, "user_id")
            seat_ids = json.loads(redis_conn.hget(hash_key, "seat_ids"))
            
            print(f"✅ Individual field retrieval - User ID: {user_id}")
            print(f"✅ Seat IDs (parsed): {seat_ids}")
            
            # Check TTL
            ttl = redis_conn.ttl(hash_key)
            print(f"✅ Cart TTL: {ttl} seconds")
            
        else:
            print("❌ Failed to retrieve cart data")
            return False
        
        # Cleanup
        redis_conn.delete(hash_key)
        print("✅ Hash operations cleanup completed")
        return True
        
    except Exception as e:
        print(f"❌ Hash operations failed: {e}")
        return False

def test_seat_locking_simulation():
    """Simulate the seat locking mechanism used in the app with 5-minute expiration"""
    print_separator("Testing Seat Locking Simulation (5-minute expiration)")
    
    try:
        user_id = "test-user-789"
        event_id = "1"
        seat_ids = ["A1", "A2", "B5"]
        cart_id = "cart-test-123"
        
        # Simulate cart creation (like in TicketLockingService)
        cart_key = f"cart:{user_id}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=CART_EXPIRATION_SECONDS)
        
        cart_data = {
            "cart_id": cart_id,
            "user_id": user_id,
            "event_id": event_id,
            "seat_ids": json.dumps(seat_ids),
            "status": "locked",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat()
        }
        
        # Use pipeline for atomic operations
        pipe = redis_conn.pipeline()
        
        # Store cart data with 5-minute expiration
        pipe.hset(cart_key, mapping=cart_data)
        pipe.expire(cart_key, CART_EXPIRATION_SECONDS)
        
        # Store individual seat locks with 5-minute expiration
        for seat_id in seat_ids:
            seat_lock_key = f"seat_lock:{event_id}:{seat_id}"
            seat_lock_data = {
                "user_id": user_id,
                "cart_id": cart_id,
                "locked_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at.isoformat()
            }
            pipe.hset(seat_lock_key, mapping=seat_lock_data)
            pipe.expire(seat_lock_key, CART_EXPIRATION_SECONDS)
        
        # Execute all operations
        results = pipe.execute()
        print(f"✅ Pipeline executed successfully: {len(results)} operations")
        
        # Verify data was stored
        stored_cart = redis_conn.hgetall(cart_key)
        print(f"✅ Cart stored: {stored_cart['cart_id']} for user {stored_cart['user_id']}")
        
        # Check seat locks
        locked_seats = []
        for seat_id in seat_ids:
            seat_lock_key = f"seat_lock:{event_id}:{seat_id}"
            if redis_conn.exists(seat_lock_key):
                lock_data = redis_conn.hgetall(seat_lock_key)
                ttl = redis_conn.ttl(seat_lock_key)
                locked_seats.append(f"{seat_id} (locked by {lock_data['user_id']}, expires in {ttl}s)")
        
        print(f"✅ Seat locks verified: {locked_seats}")
        
        # Show cart TTL
        cart_ttl = redis_conn.ttl(cart_key)
        print(f"✅ Cart will expire in {cart_ttl} seconds ({cart_ttl//60}m {cart_ttl%60}s)")
        
        # Show current database state
        all_keys = redis_conn.keys("*")
        print(f"✅ Total keys in database: {len(all_keys)}")
        
        print("🔥 NO CLEANUP - Data will expire naturally in 5 minutes!")
        print("💡 Check keys again with: python -c \"from Database.redis_client import redis_conn; print([k for k in redis_conn.keys('*')])\"")
        
        return True
        
    except Exception as e:
        print(f"❌ Seat locking simulation failed: {e}")
        return False

def test_redis_info():
    """Display Redis server information"""
    print_separator("Redis Server Information")
    
    try:
        info = redis_conn.info()
        
        print(f"Redis Version: {info.get('redis_version', 'Unknown')}")
        print(f"Used Memory: {info.get('used_memory_human', 'Unknown')}")
        print(f"Connected Clients: {info.get('connected_clients', 'Unknown')}")
        print(f"Total Commands Processed: {info.get('total_commands_processed', 'Unknown')}")
        print(f"Keyspace Hits: {info.get('keyspace_hits', 'Unknown')}")
        print(f"Keyspace Misses: {info.get('keyspace_misses', 'Unknown')}")
        
        # Check current database
        db_info = redis_conn.info('keyspace')
        if db_info:
            print(f"Database Info: {db_info}")
        else:
            print("Database: Empty (no keys)")
            
        return True
        
    except Exception as e:
        print(f"❌ Failed to get Redis info: {e}")
        return False

def test_persistent_data():
    """Create some persistent test data to show database is working"""
    print_separator("Creating Persistent Test Data")
    
    try:
        # Create some data that won't be cleaned up
        test_data = [
            ("persistent:user:123", "john_doe"),
            ("persistent:session:abc", "active_session"),
            ("persistent:counter", "42")
        ]
        
        for key, value in test_data:
            redis_conn.set(key, value)
            # Set longer expiration (10 minutes) 
            redis_conn.expire(key, 600)
        
        print(f"✅ Created {len(test_data)} persistent test keys")
        
        # Show current key count
        all_keys = redis_conn.keys("*")
        print(f"✅ Total keys in database: {len(all_keys)}")
        
        if all_keys:
            print("Keys currently in database:")
            for key in sorted(all_keys):
                ttl = redis_conn.ttl(key)
                ttl_info = f" (expires in {ttl}s)" if ttl > 0 else " (no expiration)" if ttl == -1 else " (expired)"
                print(f"   - {key}{ttl_info}")
        
        # Check database info again
        db_info = redis_conn.info('keyspace')
        if db_info:
            print(f"✅ Database now shows: {db_info}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to create persistent data: {e}")
        return False

def main():
    """Run seat locking simulation only"""
    print("🔧 Redis Seat Locking Simulation (5-minute expiration)")
    print(f"Cart Expiration Time: {CART_EXPIRATION_SECONDS} seconds ({CART_EXPIRATION_SECONDS//60} minutes)")
    
    tests = [
        ("Connection Test", test_basic_connection),
        ("Seat Locking Simulation", test_seat_locking_simulation),
        ("Redis Info", test_redis_info)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
            
            if not success and test_name == "Connection Test":
                print("\n❌ Connection failed - skipping remaining tests")
                break
                
        except Exception as e:
            print(f"❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print_separator("Test Results Summary")
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Redis is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check Redis configuration.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)