from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from models import (
    BulkTicket, BulkTicketCreate, BulkTicketRead, 
    UserTicket, UserTicketCreate, 
    RedisOrderItem,
    UserOrder, Event, Venue,
    SeatType, TicketStatus, SeatID
)
import json
import hashlib
from utils.seat_utils import json_str_to_seat_list

class TicketService:
    @staticmethod
    def create_bulk_tickets(session: Session, bulk_ticket_data: BulkTicketCreate) -> BulkTicket:
        """Create bulk tickets for an event (organizer function)"""
        
        # Check if bulk ticket already exists
        existing = session.exec(
            select(BulkTicket).where(
                BulkTicket.event_id == bulk_ticket_data.event_id,
                BulkTicket.venue_id == bulk_ticket_data.venue_id,
                BulkTicket.seat_type == bulk_ticket_data.seat_type,
                BulkTicket.seat_prefix == bulk_ticket_data.seat_prefix
            )
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400, 
                detail=f"Bulk ticket already exists for {bulk_ticket_data.seat_type} seats with prefix {bulk_ticket_data.seat_prefix}"
            )
        
        db_bulk_ticket = BulkTicket.model_validate(bulk_ticket_data)
        session.add(db_bulk_ticket)
        session.commit()
        session.refresh(db_bulk_ticket)
        return db_bulk_ticket
    
    @staticmethod
    def get_bulk_ticket(session: Session, bulk_ticket_id: int) -> Optional[BulkTicket]:
        """Get bulk ticket by ID"""
        return session.get(BulkTicket, bulk_ticket_id)
    
    @staticmethod
    def get_available_seats(session: Session, bulk_ticket_id: int) -> List[str]:
        """Get list of available seat IDs for a bulk ticket"""
        bulk_ticket = session.get(BulkTicket, bulk_ticket_id)
        if not bulk_ticket:
            raise HTTPException(status_code=404, detail="Bulk ticket not found")
        
        # Get already sold seats
        sold_seats = session.exec(
            select(UserTicket.seat_id).where(UserTicket.bulk_ticket_id == bulk_ticket_id)
        ).all()
        
        # Generate all possible seat IDs
        all_seats = []
        for i in range(1, bulk_ticket.total_seats + 1):
            seat_id = f"{bulk_ticket.seat_prefix}{i:03d}"  # e.g., A001, B001, VIP001
            all_seats.append(seat_id)
        
        # Return available seats
        available_seats = [seat for seat in all_seats if seat not in sold_seats]
        return available_seats
    
    @staticmethod
    def generate_qr_code_data(firebase_uid: str, bulk_ticket: BulkTicket, event: Event, venue: Venue, seat: SeatID) -> str:
        """Generate QR code data with comprehensive ticket information"""
        qr_data = {
            "ticket_id": f"{seat.to_string()}-{bulk_ticket.id}",
            "seat": {"section": seat.section, "row_id": seat.row_id, "col_id": seat.col_id},
            "firebase_uid": firebase_uid,
            "event_name": event.name,
            "event_date": event.event_date.isoformat(),
            "venue_name": venue.name,
            "venue_address": venue.address,
            "seat_type": bulk_ticket.seat_type,
            "price": bulk_ticket.price
        }
        
        # Create a hash for verification
        qr_string = json.dumps(qr_data, sort_keys=True)
        hash_object = hashlib.sha256(qr_string.encode())
        qr_data["verification_hash"] = hash_object.hexdigest()[:16]
        
        return json.dumps(qr_data)
    
    @staticmethod
    def create_user_tickets_from_order(
        session: Session, 
        order: UserOrder, 
        cart_items: List[RedisOrderItem]
    ) -> List[UserTicket]:
        """Create individual user tickets from Redis cart items after order completion"""
        user_tickets = []
        
        for cart_item in cart_items:
            bulk_ticket = session.get(BulkTicket, cart_item.bulk_ticket_id)
            if not bulk_ticket:
                raise HTTPException(status_code=404, detail=f"Bulk ticket {cart_item.bulk_ticket_id} not found")
            
            event = session.get(Event, bulk_ticket.event_id)
            venue = session.get(Venue, bulk_ticket.venue_id)
            
            # Use the specific seat IDs from Redis cart (they were already locked)
            assigned_seats = cart_item.seat_ids  # Already SeatID objects
            
            if len(assigned_seats) != cart_item.quantity:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Seat count mismatch for bulk ticket {cart_item.bulk_ticket_id}"
                )
            
            # Create user tickets
            for seat in assigned_seats:
                qr_code_data = TicketService.generate_qr_code_data(
                    order.firebase_uid, bulk_ticket, event, venue, seat
                )
                
                user_ticket_data = UserTicketCreate(
                    order_id=order.id,
                    bulk_ticket_id=cart_item.bulk_ticket_id,
                    firebase_uid=order.firebase_uid,
                    seat_id=seat.to_json_str(),  # Store as JSON string
                    price_paid=cart_item.price_per_seat,
                    status=TicketStatus.SOLD
                )
                
                db_user_ticket = UserTicket.model_validate(user_ticket_data)
                db_user_ticket.qr_code_data = qr_code_data
                session.add(db_user_ticket)
                user_tickets.append(db_user_ticket)
            
            # Update bulk ticket available seats
            bulk_ticket.available_seats -= len(assigned_seats)
            session.add(bulk_ticket)
        
        session.commit()
        
        # Refresh all tickets
        for ticket in user_tickets:
            session.refresh(ticket)
        
        return user_tickets
    
    @staticmethod
    def get_user_tickets(session: Session, firebase_uid: str) -> List[dict]:
        """Get all tickets owned by a user with order_id, qr_code_data, and bulk ticket details"""
        statement = select(UserTicket).where(UserTicket.firebase_uid == firebase_uid)
        user_tickets = session.exec(statement).all()
        
        result = []
        for ticket in user_tickets:
            bulk_ticket = session.get(BulkTicket, ticket.bulk_ticket_id)
            event = session.get(Event, bulk_ticket.event_id)
            venue = session.get(Venue, bulk_ticket.venue_id)
            
            # Parse seat from JSON
            try:
                seat = ticket.get_seat_object()
                seat_dict = {"section": seat.section, "row_id": seat.row_id, "col_id": seat.col_id}
            except:
                seat_dict = ticket.seat_id  # Fallback to raw value if parsing fails
            
            ticket_details = {
                "id": ticket.id,
                "order_id": ticket.order_id,
                "qr_code_data": ticket.qr_code_data,
                "seat": seat_dict,  # Return as structured object
                "price_paid": ticket.price_paid,
                "status": ticket.status,
                "created_at": ticket.created_at,
                "bulk_ticket": {
                    "id": bulk_ticket.id,
                    "event_id": bulk_ticket.event_id,
                    "venue_id": bulk_ticket.venue_id,
                    "seat_type": bulk_ticket.seat_type,
                    "price": bulk_ticket.price,
                    "seat_prefix": bulk_ticket.seat_prefix
                }
            }
            result.append(ticket_details)
            
        return result
    
    @staticmethod
    def get_ticket_with_details(session: Session, ticket_id: int, firebase_uid: str) -> dict:
        """Get ticket with full event and venue details"""
        ticket = session.get(UserTicket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        # Security check: Ensure the user owns this ticket
        if ticket.firebase_uid != firebase_uid:
            raise HTTPException(
                status_code=403, 
                detail="You don't have permission to access this ticket"
            )
        
        bulk_ticket = session.get(BulkTicket, ticket.bulk_ticket_id)
        event = session.get(Event, bulk_ticket.event_id)
        venue = session.get(Venue, bulk_ticket.venue_id)
        
        return {
            "ticket": ticket,
            "event": event,
            "venue": venue,
            "bulk_ticket": bulk_ticket
        }
    
    @staticmethod
    def get_bulk_ticket_prices_by_venue_event(session: Session, venue_id: int, event_id: int) -> List[dict]:
        """Get all bulk ticket prices for a specific venue and event, grouped by section"""
        statement = select(BulkTicket).where(
            BulkTicket.venue_id == venue_id,
            BulkTicket.event_id == event_id
        )
        bulk_tickets = session.exec(statement).all()
        
        if not bulk_tickets:
            raise HTTPException(
                status_code=404, 
                detail=f"No bulk tickets found for venue_id={venue_id} and event_id={event_id}"
            )
        
        # Create list of dictionaries with section as key, price as value, and bulk_ticket_id
        result = []
        for bulk_ticket in bulk_tickets:
            result.append({
                "section": bulk_ticket.seat_prefix,
                "price": bulk_ticket.price,
                "bulk_ticket_id": bulk_ticket.id
            })
        
        return result
