from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from models import (
    BulkTicket, BulkTicketCreate, BulkTicketRead, 
    UserTicket, UserTicketCreate, 
    CartItem, CartItemCreate,
    UserOrder,
    SeatType, TicketStatus
)
import json
import hashlib

class TicketService:
    @staticmethod
    def create_bulk_ticket(session: Session, bulk_ticket_data: BulkTicketCreate) -> BulkTicket:
        """Create bulk tickets for an external event (references Event/Venue Service)"""
        # Note: We don't verify external event/venue existence here
        # That validation should be done by the calling service
        
        db_bulk_ticket = BulkTicket.model_validate(bulk_ticket_data.model_dump())
        session.add(db_bulk_ticket)
        session.commit()
        session.refresh(db_bulk_ticket)
        return db_bulk_ticket

    @staticmethod
    def get_bulk_tickets(session: Session, skip: int = 0, limit: int = 100) -> List[BulkTicket]:
        """Get all bulk tickets"""
        statement = select(BulkTicket).offset(skip).limit(limit)
        return session.exec(statement).all()

    @staticmethod
    def get_bulk_ticket(session: Session, bulk_ticket_id: int) -> Optional[BulkTicket]:
        """Get a specific bulk ticket"""
        return session.get(BulkTicket, bulk_ticket_id)

    @staticmethod
    def get_bulk_tickets_by_external_event(session: Session, external_event_id: int) -> List[BulkTicket]:
        """Get all bulk tickets for an external event"""
        statement = select(BulkTicket).where(BulkTicket.external_event_id == external_event_id)
        return session.exec(statement).all()
        
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
    def generate_qr_code_data(firebase_uid: str, bulk_ticket: BulkTicket, seat_id: str, external_event_info: dict = None) -> str:
        """Generate QR code data with comprehensive ticket information"""
        qr_data = {
            "ticket_id": f"{seat_id}-{bulk_ticket.id}",
            "seat_id": seat_id,
            "firebase_uid": firebase_uid,
            "external_event_id": bulk_ticket.external_event_id,
            "external_venue_id": bulk_ticket.external_venue_id,
            "seat_type": bulk_ticket.seat_type,
            "price": bulk_ticket.price
        }
        
        # Add external event info if provided (from Event/Venue Service)
        if external_event_info:
            qr_data.update(external_event_info)
        
        # Create a hash for verification
        qr_string = json.dumps(qr_data, sort_keys=True)
        hash_object = hashlib.sha256(qr_string.encode())
        qr_data["verification_hash"] = hash_object.hexdigest()[:16]
        
        return json.dumps(qr_data)
    
    @staticmethod
    def create_user_tickets_from_order(
        session: Session, 
        order: UserOrder, 
        cart_items: List[CartItem]
    ) -> List[UserTicket]:
        """Create individual user tickets from cart items after order completion"""
        user_tickets = []
        
        # Note: Firebase UID validation is handled by the calling service layer
        
        for cart_item in cart_items:
            bulk_ticket = session.get(BulkTicket, cart_item.bulk_ticket_id)
            if not bulk_ticket:
                raise HTTPException(status_code=404, detail=f"Bulk ticket {cart_item.bulk_ticket_id} not found")
            
            # Parse preferred seat IDs
            try:
                preferred_seats = json.loads(cart_item.preferred_seat_ids)
            except json.JSONDecodeError:
                preferred_seats = []
            
            # Get available seats
            available_seats = TicketService.get_available_seats(session, cart_item.bulk_ticket_id)
            
            # Assign seats (prefer user's choice, fallback to available)
            assigned_seats = []
            for preferred_seat in preferred_seats[:cart_item.quantity]:
                if preferred_seat in available_seats:
                    assigned_seats.append(preferred_seat)
                    available_seats.remove(preferred_seat)
            
            # Fill remaining with any available seats
            while len(assigned_seats) < cart_item.quantity and available_seats:
                assigned_seats.append(available_seats.pop(0))
            
            if len(assigned_seats) < cart_item.quantity:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Not enough available seats for bulk ticket {cart_item.bulk_ticket_id}"
                )
            
            # Create user tickets
            for seat_id in assigned_seats:
                qr_code_data = TicketService.generate_qr_code_data(order.firebase_uid, bulk_ticket, seat_id)
                
                user_ticket_data = UserTicketCreate(
                    order_id=order.id,
                    bulk_ticket_id=cart_item.bulk_ticket_id,
                    firebase_uid=order.firebase_uid,
                    seat_id=seat_id,
                    price_paid=bulk_ticket.price,
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
    def get_user_tickets(session: Session, user_id: int) -> List[UserTicket]:
        """Get all tickets owned by a user"""
        statement = select(UserTicket).where(UserTicket.user_id == user_id)
        return session.exec(statement).all()
    
    @staticmethod
    def get_ticket_with_details(session: Session, ticket_id: int) -> dict:
        """Get ticket with bulk ticket details (external event/venue info would come from Event/Venue Service)"""
        ticket = session.get(UserTicket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        bulk_ticket = session.get(BulkTicket, ticket.bulk_ticket_id)
        
        return {
            "ticket": ticket,
            "bulk_ticket": bulk_ticket,
            "external_event_id": bulk_ticket.external_event_id,
            "external_venue_id": bulk_ticket.external_venue_id
        }
