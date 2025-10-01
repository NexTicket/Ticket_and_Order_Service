from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from typing import List
from database import get_session
from models import (
    BulkTicket, BulkTicketCreate, BulkTicketRead,
    SeatType
)
from Ticket.services.ticket_service import TicketService

router = APIRouter()

# Note: Venues and Events are managed by the Event/Venue Service
# This service only handles bulk tickets that reference external events/venues

@router.post("/bulk-tickets/", response_model=BulkTicketRead, status_code=status.HTTP_201_CREATED)
def create_bulk_tickets_for_external_event(
    external_event_id: int,
    external_venue_id: int,
    seat_type: SeatType,
    price: float,
    total_seats: int,
    seat_prefix: str,
    session: Session = Depends(get_session)
):
    """Create bulk tickets for an external event (from Event/Venue Service)"""
    bulk_ticket_data = BulkTicketCreate(
        external_event_id=external_event_id,
        external_venue_id=external_venue_id,
        seat_type=seat_type,
        price=price,
        total_seats=total_seats,
        available_seats=total_seats,  # Initially all seats are available
        seat_prefix=seat_prefix
    )
    return TicketService.create_bulk_ticket(session, bulk_ticket_data)

@router.get("/bulk-tickets/", response_model=List[BulkTicketRead])
def get_bulk_tickets(skip: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    """Get all bulk tickets"""
    return TicketService.get_bulk_tickets(session, skip, limit)

@router.get("/bulk-tickets/event/{external_event_id}", response_model=List[BulkTicketRead])
def get_bulk_tickets_by_external_event(
    external_event_id: int, 
    session: Session = Depends(get_session)
):
    """Get bulk tickets for a specific external event"""
    return TicketService.get_bulk_tickets_by_external_event(session, external_event_id)

@router.get("/bulk-tickets/{bulk_ticket_id}/available-seats")
def get_available_seats(bulk_ticket_id: int, session: Session = Depends(get_session)):
    """Get available seat IDs for a bulk ticket"""
    available_seats = TicketService.get_available_seats(session, bulk_ticket_id)
    return {
        "bulk_ticket_id": bulk_ticket_id,
        "available_seats": available_seats,
        "count": len(available_seats)
    }
