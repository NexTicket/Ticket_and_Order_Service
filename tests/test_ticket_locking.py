"""
Test script for Ticket Locking functionality
Run this to test the Redis-based seat locking system
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000/api/ticket-locking"
# You'll need to replace this with a valid Firebase token for testing
TEST_TOKEN = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImU4MWYwNTJhZWYwNDBhOTdjMzlkMjY1MzgxZGU2Y2I0MzRiYzM1ZjMiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vbmV4dGlja2V0LWMyYzQ3IiwiYXVkIjoibmV4dGlja2V0LWMyYzQ3IiwiYXV0aF90aW1lIjoxNzU5ODY2MDc1LCJ1c2VyX2lkIjoibXpuQVdmRHlXcWM2N3g0T2RjcGNjQ1VQV3ViMiIsInN1YiI6Im16bkFXZkR5V3FjNjd4NE9kY3BjY0NVUFd1YjIiLCJpYXQiOjE3NTk4NjYwNzUsImV4cCI6MTc1OTg2OTY3NSwiZW1haWwiOiJ0ZXN0Y3VzQGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjpmYWxzZSwiZmlyZWJhc2UiOnsiaWRlbnRpdGllcyI6eyJlbWFpbCI6WyJ0ZXN0Y3VzQGdtYWlsLmNvbSJdfSwic2lnbl9pbl9wcm92aWRlciI6InBhc3N3b3JkIn19.Pe-SBbm3fX0_PwXsx8_WOkxGghXN85NK2jaiATKA4bRbbrFx-pIqMKg7OwRlXN3yNzgLFDYxNvTw-frKj9ovZuS-nJehCCb-LTc39kXMCqCGLfde5vWZDOy4Z_xlQLdsIfwVy3GJ_whwE21L509iCAYKt2tjo7BoPWOgreBVMumxERbF_35vILzeo6xgh28To90r-feK29qz9KscTFtGsITbeqJEaoD1JT91yJQBFumSUizRLlpbgw-FqVU4pamFOGN9sDAetdrUiy8ovQj88GE9aq4fdIT3coSrUPu0oBqX-XmAzw34Pdn4FWs1_537StLGbEUWCNRCIMbFHM36RA"
headers = {
    "Authorization": f"Bearer {TEST_TOKEN}",
    "Content-Type": "application/json"
}

def test_lock_seats():
    """Test locking seats"""
    print("🔒 Testing seat locking...")
    
    payload = {
        "seat_ids": ["A1", "A2", "A3"],
        "event_id": 1
    }
    
    response = requests.post(f"{BASE_URL}/lock-seats", json=payload, headers=headers)
    
    if response.status_code == 201:
        result = response.json()
        print(f"✅ Seats locked successfully!")
        print(f"   Order ID: {result['order_id']}")
        print(f"   Expires in: {result['expires_in_seconds']} seconds")
        print(f"   Expires at: {result['expires_at']}")
        return result['order_id']
    else:
        print(f"❌ Failed to lock seats: {response.status_code}")
        print(f"   Error: {response.text}")
        return None

def test_get_locked_seats():
    """Test getting current locked seats"""
    print("\n📋 Testing get locked seats...")
    
    response = requests.get(f"{BASE_URL}/locked-seats", headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        if result:
            print(f"✅ Found locked seats:")
            print(f"   Order ID: {result['order_id']}")
            print(f"   Seats: {result['seat_ids']}")
            print(f"   Remaining: {result['remaining_seconds']} seconds")
        else:
            print("ℹ️ No locked seats found")
        return result
    else:
        print(f"❌ Failed to get locked seats: {response.status_code}")
        print(f"   Error: {response.text}")
        return None

def test_check_availability():
    """Test checking seat availability"""
    print("\n🔍 Testing seat availability check...")
    
    payload = {
        "event_id": 1,
        "seat_ids": ["A1", "A2", "A3", "A4", "A5"]
    }
    
    response = requests.post(f"{BASE_URL}/check-availability", json=payload, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Availability check successful:")
        print(f"   Available: {result['available_seats']}")
        print(f"   Locked: {len(result['locked_seats'])} seats")
        print(f"   Unavailable: {result['unavailable_seats']}")
        return result
    else:
        print(f"❌ Failed to check availability: {response.status_code}")
        print(f"   Error: {response.text}")
        return None

def test_extend_lock(order_id):
    """Test extending lock time"""
    print(f"\n⏰ Testing lock extension for order {order_id}...")
    
    payload = {
        "order_id": order_id,
        "additional_seconds": 300  # 5 more minutes
    }
    
    response = requests.post(f"{BASE_URL}/extend-lock", json=payload, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Lock extended successfully!")
        print(f"   New expires at: {result['new_expires_at']}")
        print(f"   Total remaining: {result['total_remaining_seconds']} seconds")
        return True
    else:
        print(f"❌ Failed to extend lock: {response.status_code}")
        print(f"   Error: {response.text}")
        return False

def test_unlock_seats(order_id):
    """Test unlocking seats"""
    print(f"\n🔓 Testing seat unlocking for order {order_id}...")
    
    payload = {
        "order_id": order_id
    }
    
    response = requests.post(f"{BASE_URL}/unlock-seats", json=payload, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Seats unlocked successfully!")
        print(f"   Unlocked seats: {result['unlocked_seat_ids']}")
        return True
    else:
        print(f"❌ Failed to unlock seats: {response.status_code}")
        print(f"   Error: {response.text}")
        return False

def test_final_persistent_lock():
    """Lock 4 seats and leave them until expiration"""
    print("\n🔐 Final Test: Locking 4 seats for persistence...")
    
    payload = {
        "seat_ids": ["B1", "B2", "B3", "B4"],
        "event_id": 1
    }
    
    response = requests.post(f"{BASE_URL}/lock-seats", json=payload, headers=headers)
    
    if response.status_code == 201:
        result = response.json()
        print(f"✅ Final seats locked successfully!")
        print(f"   Order ID: {result['order_id']}")
        print(f"   Seats: {payload['seat_ids']}")
        print(f"   Expires in: {result['expires_in_seconds']} seconds ({result['expires_in_seconds']//60}m {result['expires_in_seconds']%60}s)")
        print(f"   Expires at: {result['expires_at']}")
        print(f"🔥 These seats will remain locked until expiration!")
        print(f"💡 Monitor with Redis keys: order:{result.get('user_id', 'unknown')} and seat_lock:1:B1-B4")
        return result['order_id']
    else:
        print(f"❌ Failed to lock final seats: {response.status_code}")
        print(f"   Error: {response.text}")
        return None

def main():
    """Run all tests"""
    print("🚀 Starting Ticket Locking Tests...")
    print("=" * 50)
    
    # Test 1: Lock seats
    order_id = test_lock_seats()
    if not order_id:
        print("❌ Cannot continue tests without a valid order_id")
        return
    
    # Test 2: Get locked seats
    time.sleep(1)  # Small delay
    test_get_locked_seats()
    
    # Test 3: Check availability
    time.sleep(1)
    test_check_availability()
    
    # Test 4: Extend lock
    time.sleep(1)
    test_extend_lock(order_id)
    
    # Test 5: Get locked seats again to see extension
    time.sleep(1)
    test_get_locked_seats()
    
    # Test 6: Unlock seats
    time.sleep(1)
    test_unlock_seats(order_id)
    
    # Test 7: Verify seats are unlocked
    time.sleep(1)
    test_get_locked_seats()
    
    # Final Test: Lock 4 seats and leave them
    time.sleep(1)
    final_order_id = test_final_persistent_lock()
    
    print("\n" + "=" * 50)
    print("🎉 All tests completed!")
    if final_order_id:
        print(f"🔐 4 seats (B1-B4) remain locked with order ID: {final_order_id}")
        print(f"⏰ They will expire automatically in 5 minutes")

if __name__ == "__main__":
    print("⚠️  Make sure to:")
    print("1. Start your FastAPI server")
    print("2. Start Redis server")
    print("3. Replace TEST_TOKEN with a valid Firebase token")
    print("4. Ensure you have the required dependencies installed")
    print()
    
    # Run the tests
    main()
    
    print("✅ Test execution completed!")