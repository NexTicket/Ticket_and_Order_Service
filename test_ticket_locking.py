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
TEST_TOKEN = "your_firebase_token_here"

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
        print(f"   Cart ID: {result['cart_id']}")
        print(f"   Expires in: {result['expires_in_seconds']} seconds")
        print(f"   Expires at: {result['expires_at']}")
        return result['cart_id']
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
            print(f"   Cart ID: {result['cart_id']}")
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

def test_extend_lock(cart_id):
    """Test extending lock time"""
    print(f"\n⏰ Testing lock extension for cart {cart_id}...")
    
    payload = {
        "cart_id": cart_id,
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

def test_unlock_seats(cart_id):
    """Test unlocking seats"""
    print(f"\n🔓 Testing seat unlocking for cart {cart_id}...")
    
    payload = {
        "cart_id": cart_id
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

def main():
    """Run all tests"""
    print("🚀 Starting Ticket Locking Tests...")
    print("=" * 50)
    
    # Test 1: Lock seats
    cart_id = test_lock_seats()
    if not cart_id:
        print("❌ Cannot continue tests without a valid cart_id")
        return
    
    # Test 2: Get locked seats
    time.sleep(1)  # Small delay
    test_get_locked_seats()
    
    # Test 3: Check availability
    time.sleep(1)
    test_check_availability()
    
    # Test 4: Extend lock
    time.sleep(1)
    test_extend_lock(cart_id)
    
    # Test 5: Get locked seats again to see extension
    time.sleep(1)
    test_get_locked_seats()
    
    # Test 6: Unlock seats
    time.sleep(1)
    test_unlock_seats(cart_id)
    
    # Test 7: Verify seats are unlocked
    time.sleep(1)
    test_get_locked_seats()
    
    print("\n" + "=" * 50)
    print("🎉 All tests completed!")

if __name__ == "__main__":
    print("⚠️  Make sure to:")
    print("1. Start your FastAPI server")
    print("2. Start Redis server")
    print("3. Replace TEST_TOKEN with a valid Firebase token")
    print("4. Ensure you have the required dependencies installed")
    print()
    
    # Uncomment the line below when you're ready to run tests
    # main()
    
    print("Update the TEST_TOKEN variable and uncomment main() to run tests.")