"""
Test script to send a ticket.generated message to Kafka
This simulates what happens when an order is completed and tickets are generated.
"""
import json
import sys
import os

# Add parent directory to path to import kafka_producer
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kafka.kafka_producer import send_message, flush_producer, close

def test_send_ticket_notification():
    """
    Test sending a ticket.generated notification to Kafka
    """
    print("=" * 60)
    print("Testing Kafka Ticket Notification")
    print("=" * 60)
    
    # Sample QR data as it would be stored in the database
    qr_data = {
        "ticket_id": "ticket_abc123_Section6:R8:C15",
        "event_id": 1,
        "venue_id": 1,
        "seat": {
            "section": "Section 6",
            "row_id": 8,
            "col_id": 15
        },
        "firebase_uid": "lHdA8LDmVpemAXKvC5Huv5aQ6Pk1",
        "order_ref": "ORD-ABC123DEF"
    }
    
    # Create the notification data matching the consumer's expected format
    # Note: timestamp and messageId will be automatically added by send_message()
    notification_data = {
        "eventType": "ticket.generated",
        "ticketId": "ticket_abc123_Section6:R8:C15",
        "orderId": "abc123-def456-ghi789",
        "firebaseUid": "lHdA8LDmVpemAXKvC5Huv5aQ6Pk1",
        "eventId": "1",
        "venueId": "1",
        "qrData": json.dumps(qr_data)
    }
    
    print("\nSending notification with data:")
    print(json.dumps(notification_data, indent=2))
    print("\nNote: 'timestamp' and 'messageId' will be added automatically by the producer")
    
    try:
        # Send the message
        success = send_message(
            topic="ticket_notifications",
            key="lHdA8LDmVpemAXKvC5Huv5aQ6Pk1",  # Use firebase_uid as key
            data=notification_data,
            headers={
                "service": b"ticket-order-service",
                "message_type": b"ticket_generated"
            }
        )
        
        if success:
            print("\n✓ Message sent successfully!")
            
            # Flush to ensure message is delivered
            print("\nFlushing producer to ensure delivery...")
            flush_producer(timeout=5.0)
            print("✓ Producer flushed successfully")
            
        else:
            print("\n✗ Failed to send message")
            return False
            
    except Exception as e:
        print(f"\n✗ Error sending message: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up
        print("\nClosing Kafka producer...")
        close()
        print("✓ Producer closed")
    
    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)
    return True


def test_send_multiple_tickets():
    """
    Test sending multiple ticket notifications (simulating an order with 2 tickets)
    """
    print("\n" + "=" * 60)
    print("Testing Multiple Ticket Notifications (Order with 2 tickets)")
    print("=" * 60)
    
    firebase_uid = "lHdA8LDmVpemAXKvC5Huv5aQ6Pk1"
    order_id = "test-order-multiple-123"
    
    # Simulate 2 tickets in an order
    tickets = [
        {
            "ticketId": f"ticket_{order_id}_Section6:R8:C15",
            "seat": {"section": "Section 6", "row_id": 8, "col_id": 15},
            "event_id": 1,
            "venue_id": 1
        },
        {
            "ticketId": f"ticket_{order_id}_Section6:R8:C16",
            "seat": {"section": "Section 6", "row_id": 8, "col_id": 16},
            "event_id": 1,
            "venue_id": 1
        }
    ]
    
    successful = 0
    failed = 0
    
    for i, ticket in enumerate(tickets, 1):
        print(f"\n--- Sending Ticket {i}/{len(tickets)} ---")
        
        # Create QR data
        qr_data = {
            "ticket_id": ticket["ticketId"],
            "event_id": ticket["event_id"],
            "venue_id": ticket["venue_id"],
            "seat": ticket["seat"],
            "firebase_uid": firebase_uid,
            "order_ref": order_id
        }
        
        # Create notification
        notification_data = {
            "eventType": "ticket.generated",
            "ticketId": ticket["ticketId"],
            "orderId": order_id,
            "firebaseUid": firebase_uid,
            "eventId": str(ticket["event_id"]),
            "venueId": str(ticket["venue_id"]),
            "qrData": json.dumps(qr_data)
        }
        
        print(f"Ticket ID: {ticket['ticketId']}")
        print(f"Seat: {ticket['seat']}")
        
        try:
            success = send_message(
                topic="ticket_notifications",
                key=firebase_uid,
                data=notification_data,
                headers={
                    "service": b"ticket-order-service",
                    "message_type": b"ticket_generated"
                }
            )
            
            if success:
                print(f"✓ Ticket {i} sent successfully")
                successful += 1
            else:
                print(f"✗ Ticket {i} failed to send")
                failed += 1
                
        except Exception as e:
            print(f"✗ Error sending ticket {i}: {e}")
            failed += 1
    
    # Flush all messages
    print("\nFlushing producer...")
    flush_producer(timeout=5.0)
    
    # Clean up
    close()
    
    print("\n" + "=" * 60)
    print(f"Results: {successful} successful, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    print("\nKafka Ticket Notification Test Script")
    print("=" * 60)
    print("This script tests sending ticket.generated messages to Kafka")
    print("Make sure Kafka is running before executing this test")
    print("=" * 60)
    
    # Ask user which test to run
    print("\nSelect test to run:")
    print("1. Send single ticket notification")
    print("2. Send multiple ticket notifications (2 tickets)")
    print("3. Run both tests")
    
    choice = input("\nEnter choice (1/2/3): ").strip()
    
    if choice == "1":
        test_send_ticket_notification()
    elif choice == "2":
        test_send_multiple_tickets()
    elif choice == "3":
        print("\n" + "=" * 60)
        print("Running Test 1: Single Ticket")
        print("=" * 60)
        test_send_ticket_notification()
        
        print("\n\n" + "=" * 60)
        print("Running Test 2: Multiple Tickets")
        print("=" * 60)
        test_send_multiple_tickets()
    else:
        print("Invalid choice. Exiting.")
