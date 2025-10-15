from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime
from models import Event, EventCreate, EventRead, Venue, BulkTicket, BulkTicketCreate, SeatType
import json

class EventService:
    @staticmethod
    def create_event(session: Session, event_data: EventCreate) -> Event:
        """Create a new event"""
        # Verify venue exists
        venue = session.get(Venue, event_data.venue_id)
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")
        
        db_event = Event.model_validate(event_data)
        session.add(db_event)
        session.commit()
        session.refresh(db_event)
        return db_event
    
    @staticmethod
    def get_event(session: Session, event_id: int) -> Optional[Event]:
        """Get event by ID"""
        return session.get(Event, event_id)
    
    @staticmethod
    def get_events(session: Session, skip: int = 0, limit: int = 100) -> List[Event]:
        """Get all events with pagination"""
        statement = select(Event).offset(skip).limit(limit)
        return session.exec(statement).all()
    
    @staticmethod
    def create_bulk_tickets(
        session: Session, 
        event_id: int, 
        venue_id: int, 
        seat_type: SeatType, 
        price: float, 
        total_seats: int, 
        seat_prefix: str
    ) -> BulkTicket:
        """Create bulk tickets for an event"""
        # Verify event and venue exist
        event = session.get(Event, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        venue = session.get(Venue, venue_id)
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")
        
        if event.venue_id != venue_id:
            raise HTTPException(status_code=400, detail="Event venue mismatch")
        
        # Check if bulk ticket already exists for this combination
        existing = session.exec(
            select(BulkTicket).where(
                BulkTicket.event_id == event_id,
                BulkTicket.venue_id == venue_id,
                BulkTicket.seat_type == seat_type,
                BulkTicket.seat_prefix == seat_prefix
            )
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400, 
                detail=f"Bulk ticket already exists for {seat_type} seats with prefix {seat_prefix}"
            )
        
        bulk_ticket_data = BulkTicketCreate(
            event_id=event_id,
            venue_id=venue_id,
            seat_type=seat_type,
            price=price,
            total_seats=total_seats,
            available_seats=total_seats,  # Initially all seats are available
            seat_prefix=seat_prefix
        )
        
        db_bulk_ticket = BulkTicket.model_validate(bulk_ticket_data)
        session.add(db_bulk_ticket)
        session.commit()
        session.refresh(db_bulk_ticket)
        return db_bulk_ticket
    
    @staticmethod
    def get_event_bulk_tickets(session: Session, event_id: int) -> List[BulkTicket]:
        """Get all bulk tickets for an event - only uses BulkTicket table"""
        statement = select(BulkTicket).where(BulkTicket.event_id == event_id)
        bulk_tickets = session.exec(statement).all()
        
        if not bulk_tickets:
            raise HTTPException(
                status_code=404, 
                detail=f"No bulk tickets found for event_id {event_id}"
            )
        
        return bulk_tickets
    
    @staticmethod
    def get_available_seats(session: Session, bulk_ticket_id: int) -> List[str]:
        """Generate list of available seat IDs for a bulk ticket"""
        bulk_ticket = session.get(BulkTicket, bulk_ticket_id)
        if not bulk_ticket:
            raise HTTPException(status_code=404, detail="Bulk ticket not found")
        
        # Get already sold seats
        from models import UserTicket
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
