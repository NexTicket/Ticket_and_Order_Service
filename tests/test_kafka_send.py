#!/usr/bin/env python3
"""
Simple test script to test Kafka send_message functionality.
This script sends test messages to Kafka that you can monitor in Redpanda UI.
"""

import json
import time
import sys
import os

# Add the parent directory to Python path so we can import from kafka package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kafka.kafka_producer import send_message, flush_producer, close

def test_send_message():
    """Test sending messages to Kafka"""
    print("🚀 Starting Kafka send_message test...")
    
    # Test data - simulating order completion notification
    test_order_data = {
        "order_id": "test_order_123",
        "firebase_uid": "test_user_456",
        "total_amount": 150.00,
        "qr_codes": [
            json.dumps({
                "ticket_id": "ticket_test_order_123_seat_A1",
                "event_id": 1001,
                "venue_id": 2001,
                "seat_id": "A1",
                "firebase_uid": "test_user_456",
                "order_ref": "ORD-TEST-123"
            }),
            json.dumps({
                "ticket_id": "ticket_test_order_123_seat_A2",
                "event_id": 1001,
                "venue_id": 2001,
                "seat_id": "A2",
                "firebase_uid": "test_user_456",
                "order_ref": "ORD-TEST-123"
            })
        ],
        "notification_type": "order_completed"
    }
    
    # Test headers
    test_headers = {
        "service": b"ticket-order-service",
        "message_type": b"order_completed"
    }
    
    print(f"📤 Sending test message to topic: ticket_notifications")
    print(f"📋 Message key: {test_order_data['firebase_uid']}")
    print(f"📊 Message data: {json.dumps(test_order_data, indent=2)}")
    
    try:
        # Send the message
        success = send_message(
            topic="ticket_notifications",
            key=test_order_data["firebase_uid"],
            data=test_order_data,
            headers=test_headers
        )
        
        if success:
            print("✅ Message sent successfully!")
            print("🔍 Check your Redpanda UI to see the message")
            print("   - Topic: ticket_notifications")
            print(f"   - Key: {test_order_data['firebase_uid']}")
            print("   - Look for the message with timestamp around:", int(time.time()))
        else:
            print("❌ Failed to send message")
            
    except Exception as e:
        print(f"💥 Error occurred: {e}")
    
    # Wait a moment for message to be sent
    print("\n⏳ Waiting 2 seconds for message delivery...")
    time.sleep(2)
    
    # Flush any remaining messages
    print("🔄 Flushing producer...")
    flush_producer(timeout=5.0)
    
    print("✨ Test completed!")

def test_multiple_messages():
    """Test sending multiple messages"""
    print("\n🚀 Testing multiple messages...")
    
    for i in range(3):
        test_data = {
            "order_id": f"test_order_{i+1}",
            "firebase_uid": f"test_user_{i+1}",
            "total_amount": 100.0 + (i * 25),
            "message_number": i + 1,
            "test_type": "multiple_messages"
        }
        
        print(f"📤 Sending message {i+1}/3...")
        
        success = send_message(
            topic="ticket_notifications",
            key=f"test_user_{i+1}",
            data=test_data,
            headers={
                "service": b"ticket-order-service",
                "message_type": b"test_message"
            }
        )
        
        if success:
            print(f"✅ Message {i+1} sent successfully!")
        else:
            print(f"❌ Message {i+1} failed!")
        
        # Small delay between messages
        time.sleep(0.5)
    
    print("🔄 Flushing all messages...")
    flush_producer(timeout=5.0)
    print("✨ Multiple message test completed!")

if __name__ == "__main__":
    print("=" * 60)
    print("🔥 KAFKA SEND_MESSAGE TEST")
    print("=" * 60)
    
    try:
        # Test single message
        test_send_message()
        
        # Test multiple messages
        test_multiple_messages()
        
        print("\n🎉 All tests completed!")
        print("📱 Check your Redpanda Kafka UI at: http://localhost:8080")
        print("🔍 Look for messages in the 'ticket_notifications' topic")
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
    finally:
        # Clean shutdown
        print("\n🧹 Cleaning up...")
        close()
        print("👋 Goodbye!")