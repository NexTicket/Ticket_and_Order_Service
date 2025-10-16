"""
Database migration script for seat structure change
Converts seat_id from simple strings to JSON objects

IMPORTANT: Backup your database before running this!
"""

from sqlmodel import Session, select
from database import get_session
from models import UserTicket, SeatOrder
import json


def migrate_user_tickets():
    """
    Migrate UserTicket.seat_id from string format to JSON format
    
    This assumes your old seat_id format was something simple like "A001", "VIP015", etc.
    You may need to adjust the parsing logic based on your actual format.
    """
    session = next(get_session())
    
    try:
        # Get all user tickets
        tickets = session.exec(select(UserTicket)).all()
        
        print(f"Found {len(tickets)} tickets to migrate")
        
        migrated = 0
        skipped = 0
        errors = 0
        
        for ticket in tickets:
            try:
                # Check if already migrated (seat_id starts with '{')
                if ticket.seat_id.startswith('{'):
                    print(f"Ticket {ticket.id} already migrated, skipping")
                    skipped += 1
                    continue
                
                # CUSTOMIZE THIS LOGIC BASED ON YOUR CURRENT SEAT FORMAT
                # Example: If your seats are like "A001", "B025", "VIP015"
                # This is a placeholder - you need to implement your own parsing
                
                # Option 1: If you don't have section/row/col data, create dummy values
                seat_obj = {
                    "section": "General",  # Default section
                    "row_id": 1,  # You might parse this from your seat_id
                    "col_id": int(ticket.seat_id[-3:]) if ticket.seat_id[-3:].isdigit() else 1
                }
                
                # Option 2: If you have a specific format, parse it
                # Example for format like "Section1-R5-C12":
                # parts = ticket.seat_id.split('-')
                # seat_obj = {
                #     "section": parts[0],
                #     "row_id": int(parts[1].replace('R', '')),
                #     "col_id": int(parts[2].replace('C', ''))
                # }
                
                # Update the ticket
                ticket.seat_id = json.dumps(seat_obj)
                session.add(ticket)
                migrated += 1
                
                if migrated % 100 == 0:
                    print(f"Migrated {migrated} tickets...")
                    session.commit()
                
            except Exception as e:
                print(f"Error migrating ticket {ticket.id}: {e}")
                errors += 1
        
        session.commit()
        print(f"\nMigration complete!")
        print(f"Migrated: {migrated}")
        print(f"Skipped: {skipped}")
        print(f"Errors: {errors}")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        session.rollback()
    finally:
        session.close()


def migrate_seat_orders():
    """
    Migrate SeatOrder.seat_ids from JSON array of strings to JSON array of objects
    """
    session = next(get_session())
    
    try:
        seat_orders = session.exec(select(SeatOrder)).all()
        
        print(f"Found {len(seat_orders)} seat orders to migrate")
        
        migrated = 0
        skipped = 0
        errors = 0
        
        for seat_order in seat_orders:
            try:
                # Parse current seat_ids
                current_seats = json.loads(seat_order.seat_ids)
                
                # Check if already migrated (first element is a dict)
                if current_seats and isinstance(current_seats[0], dict):
                    print(f"SeatOrder {seat_order.id} already migrated, skipping")
                    skipped += 1
                    continue
                
                # Convert string seats to objects
                new_seats = []
                for seat_str in current_seats:
                    # CUSTOMIZE THIS BASED ON YOUR FORMAT
                    # This is a placeholder - implement your parsing logic
                    
                    seat_obj = {
                        "section": "General",
                        "row_id": 1,
                        "col_id": int(seat_str[-3:]) if len(seat_str) >= 3 and seat_str[-3:].isdigit() else 1
                    }
                    new_seats.append(seat_obj)
                
                # Update seat order
                seat_order.seat_ids = json.dumps(new_seats)
                session.add(seat_order)
                migrated += 1
                
            except Exception as e:
                print(f"Error migrating seat order {seat_order.id}: {e}")
                errors += 1
        
        session.commit()
        print(f"\nSeat order migration complete!")
        print(f"Migrated: {migrated}")
        print(f"Skipped: {skipped}")
        print(f"Errors: {errors}")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        session.rollback()
    finally:
        session.close()


def verify_migration():
    """Verify that migration was successful"""
    session = next(get_session())
    
    try:
        # Check UserTickets
        tickets = session.exec(select(UserTicket).limit(5)).all()
        print("\nSample migrated tickets:")
        for ticket in tickets:
            print(f"Ticket {ticket.id}: {ticket.seat_id}")
            # Try to parse it
            try:
                seat_data = json.loads(ticket.seat_id)
                assert 'section' in seat_data
                assert 'row_id' in seat_data
                assert 'col_id' in seat_data
                print(f"  ✓ Valid format: {seat_data}")
            except Exception as e:
                print(f"  ✗ Invalid format: {e}")
        
        # Check SeatOrders
        seat_orders = session.exec(select(SeatOrder).limit(5)).all()
        print("\nSample migrated seat orders:")
        for so in seat_orders:
            print(f"SeatOrder {so.id}: {so.seat_ids}")
            try:
                seats_data = json.loads(so.seat_ids)
                for seat in seats_data:
                    assert 'section' in seat
                    assert 'row_id' in seat
                    assert 'col_id' in seat
                print(f"  ✓ Valid format")
            except Exception as e:
                print(f"  ✗ Invalid format: {e}")
                
    finally:
        session.close()


if __name__ == "__main__":
    print("="*60)
    print("SEAT STRUCTURE MIGRATION")
    print("="*60)
    print("\nWARNING: This will modify your database!")
    print("Make sure you have a backup before proceeding.\n")
    
    response = input("Do you want to proceed? (yes/no): ")
    
    if response.lower() != 'yes':
        print("Migration cancelled.")
        exit()
    
    print("\n" + "="*60)
    print("Step 1: Migrating UserTickets")
    print("="*60)
    migrate_user_tickets()
    
    print("\n" + "="*60)
    print("Step 2: Migrating SeatOrders")
    print("="*60)
    migrate_seat_orders()
    
    print("\n" + "="*60)
    print("Step 3: Verifying Migration")
    print("="*60)
    verify_migration()
    
    print("\n" + "="*60)
    print("MIGRATION COMPLETE!")
    print("="*60)
    print("\nDon't forget to:")
    print("1. Clear Redis cache: redis-cli FLUSHDB")
    print("2. Test the application thoroughly")
    print("3. Monitor for any issues")
