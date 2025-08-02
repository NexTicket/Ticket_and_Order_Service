from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from typing import List
from database import get_session
from models import (
    Venue, VenueCreate, VenueRead,
    Event, EventCreate, EventRead,
    BulkTicket, BulkTicketCreate, BulkTicketRead,
    SeatType
)
from Ticket.services.venue_service import VenueService
from Ticket.services.event_service import EventService
from Ticket.services.ticket_service import TicketService

router = APIRouter()

# Venue endpoints
@router.post("/venues/", response_model=VenueRead, status_code=status.HTTP_201_CREATED)
def create_venue(
    name: str,
    address: str,
    city: str,
    capacity: int,
    description: str = None,
    session: Session = Depends(get_session)
):
    """Create a new venue using query parameters"""
    venue_data = VenueCreate(
        name=name,
        address=address,
        city=city,
        capacity=capacity,
        description=description
    )
    return VenueService.create_venue(session, venue_data)

@router.get("/venues/", response_model=List[VenueRead])
def get_venues(skip: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    """Get all venues"""
    return VenueService.get_venues(session, skip, limit)

@router.get("/venues/{venue_id}", response_model=VenueRead)
def get_venue(venue_id: int, session: Session = Depends(get_session)):
    """Get venue by ID"""
    venue = VenueService.get_venue(session, venue_id)
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    return venue

@router.get("/venues/{venue_id}/events", response_model=List[EventRead])
def get_venue_events(venue_id: int, session: Session = Depends(get_session)):
    """Get all events for a venue"""
    return VenueService.get_venue_events(session, venue_id)

# Event endpoints
@router.post("/events/", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(
    name: str,
    venue_id: int,
    event_date: str,  # ISO format datetime string
    description: str = None,
    session: Session = Depends(get_session)
):
    """Create a new event using query parameters"""
    from datetime import datetime
    
    # Parse the datetime string
    try:
        parsed_date = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail="Invalid date format. Use ISO format: YYYY-MM-DDTHH:MM:SS"
        )
    
    event_data = EventCreate(
        name=name,
        venue_id=venue_id,
        event_date=parsed_date,
        description=description
    )
    return EventService.create_event(session, event_data)

@router.get("/events/", response_model=List[EventRead])
def get_events(skip: int = 0, limit: int = 100, session: Session = Depends(get_session)):
    """Get all events"""
    return EventService.get_events(session, skip, limit)

@router.get("/events/{event_id}", response_model=EventRead)
def get_event(event_id: int, session: Session = Depends(get_session)):
    """Get event by ID"""
    event = EventService.get_event(session, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event

@router.get("/events/{event_id}/bulk-tickets", response_model=List[BulkTicketRead])
def get_event_bulk_tickets(event_id: int, session: Session = Depends(get_session)):
    """Get all bulk tickets for an event"""
    return EventService.get_event_bulk_tickets(session, event_id)

# Bulk ticket endpoints
@router.post("/bulk-tickets/", response_model=BulkTicketRead, status_code=status.HTTP_201_CREATED)
def create_bulk_tickets(bulk_ticket: BulkTicketCreate, session: Session = Depends(get_session)):
    """Create bulk tickets for an event (organizer function)"""
    return TicketService.create_bulk_tickets(session, bulk_ticket)

@router.get("/bulk-tickets/{bulk_ticket_id}", response_model=BulkTicketRead)
def get_bulk_ticket(bulk_ticket_id: int, session: Session = Depends(get_session)):
    """Get bulk ticket by ID"""
    bulk_ticket = TicketService.get_bulk_ticket(session, bulk_ticket_id)
    if not bulk_ticket:
        raise HTTPException(status_code=404, detail="Bulk ticket not found")
    return bulk_ticket

@router.get("/bulk-tickets/{bulk_ticket_id}/available-seats")
def get_available_seats(bulk_ticket_id: int, session: Session = Depends(get_session)):
    """Get available seat IDs for a bulk ticket"""
    available_seats = TicketService.get_available_seats(session, bulk_ticket_id)
    return {
        "bulk_ticket_id": bulk_ticket_id,
        "available_seats": available_seats,
        "count": len(available_seats)
    }

# Organizer convenience endpoint
@router.post("/events/{event_id}/create-bulk-tickets", response_model=BulkTicketRead)
def create_bulk_tickets_for_event(
    event_id: int,
    venue_id: int,
    seat_type: SeatType,
    price: float,
    total_seats: int,
    seat_prefix: str,
    session: Session = Depends(get_session)
):
    """Convenience endpoint for organizers to create bulk tickets"""
    bulk_ticket_data = BulkTicketCreate(
        event_id=event_id,
        venue_id=venue_id,
        seat_type=seat_type,
        price=price,
        total_seats=total_seats,
        available_seats=total_seats,
        seat_prefix=seat_prefix
    )
    return TicketService.create_bulk_tickets(session, bulk_ticket_data)
