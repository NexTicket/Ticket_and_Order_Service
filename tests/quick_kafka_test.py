#!/usr/bin/env python3
"""
Quick Kafka connectivity test
"""

from kafka.kafka_producer import send_message
import time

def quick_test():
    print("🧪 Quick Kafka Test")
    print("-" * 30)
    
    # Simple test message
    test_data = {
        "test": "Hello Kafka!",
        "timestamp": int(time.time()),
        "message": "This is a test message from NexTicket Order Service"
    }
    
    print("📤 Sending test message...")
    
    try:
        result = send_message(
            topic="ticket_notifications",
            key="test_key",
            data=test_data
        )
        
        if result:
            print("✅ SUCCESS: Message sent to Kafka!")
            print("🔍 Check Redpanda UI for the message")
        else:
            print("❌ FAILED: Could not send message")
            
    except Exception as e:
        print(f"💥 ERROR: {e}")

if __name__ == "__main__":
    quick_test()