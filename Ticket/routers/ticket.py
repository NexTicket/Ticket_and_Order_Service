from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from typing import List
from database import get_session
from firebase_auth import get_current_user_from_token
from models import (
    UserTicket, UserTicketRead, 
    BulkTicket, BulkTicketRead,
    TicketWithDetails
)
from Ticket.services.ticket_service import TicketService

router = APIRouter()

@router.get("/user/tickets")
def get_user_tickets(
    current_user: dict = Depends(get_current_user_from_token),
    session: Session = Depends(get_session)
):
    """Get all tickets owned by a user with order_id, qr_code_data, and bulk ticket details"""
    firebase_uid = current_user['uid']
    return TicketService.get_user_tickets(session, firebase_uid)

@router.get("/user-ticket/{ticket_id}")
def get_ticket_details(
    ticket_id: int, 
    current_user: dict = Depends(get_current_user_from_token),
    session: Session = Depends(get_session)
):
    """Get ticket with full event and venue details"""
    firebase_uid = current_user['uid']
    return TicketService.get_ticket_with_details(session, ticket_id, firebase_uid)

@router.get("/user-ticket/{ticket_id}/qr-data")
def get_ticket_qr_data(
    ticket_id: int, 
    current_user: dict = Depends(get_current_user_from_token),
    session: Session = Depends(get_session)
):
    """Get QR code data for a specific ticket"""
    firebase_uid = current_user['uid']
    ticket = session.get(UserTicket, ticket_id)
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    # Ensure the user owns this ticket
    if ticket.firebase_uid != firebase_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You don't have permission to access this ticket"
        )
    
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
