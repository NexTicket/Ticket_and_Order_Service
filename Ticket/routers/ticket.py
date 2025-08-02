from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from typing import List
from database import get_session
from models import (
    UserTicket, UserTicketRead, 
    BulkTicket, BulkTicketRead,
    TicketWithDetails
)
from Ticket.services.ticket_service import TicketService

router = APIRouter()

@router.get("/user/{user_id}/tickets", response_model=List[UserTicketRead])
def get_user_tickets(user_id: int, session: Session = Depends(get_session)):
    """Get all tickets owned by a user"""
    return TicketService.get_user_tickets(session, user_id)

@router.get("/user-ticket/{ticket_id}")
def get_ticket_details(ticket_id: int, session: Session = Depends(get_session)):
    """Get ticket with full event and venue details"""
    return TicketService.get_ticket_with_details(session, ticket_id)

@router.get("/user-ticket/{ticket_id}/qr-data")
def get_ticket_qr_data(ticket_id: int, session: Session = Depends(get_session)):
    """Get QR code data for a specific ticket"""
    from models import UserTicket
    ticket = session.get(UserTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    return {
        "ticket_id": ticket_id,
        "qr_code_data": ticket.qr_code_data
    }

@router.get("/bulk-ticket/{bulk_ticket_id}/available-seats")
def get_bulk_ticket_available_seats(bulk_ticket_id: int, session: Session = Depends(get_session)):
    """Get available seats for a bulk ticket"""
    try:
        available_seats = TicketService.get_available_seats(session, bulk_ticket_id)
        return {
            "bulk_ticket_id": bulk_ticket_id,
            "available_seats": available_seats,
            "count": len(available_seats)
        }
    except HTTPException as e:
        raise e
