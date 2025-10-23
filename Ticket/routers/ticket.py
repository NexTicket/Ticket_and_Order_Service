from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from typing import List
from database import get_session
from firebase_auth import get_current_user_from_token
from models import (
    UserTicket, UserTicketRead, 
    BulkTicket, BulkTicketRead,
    TicketWithDetails,
    BulkTicketPriceRequest,
    TicketCheckInRequest,
    TicketCheckInResponse
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

@router.get("/bulk-ticket/prices")
def get_bulk_ticket_prices(
    request_data: BulkTicketPriceRequest,
    session: Session = Depends(get_session)
):
    """Get all bulk ticket prices for a specific venue and event
    
    Returns a list of dictionaries with section, price, and bulk_ticket_id.
    Example: [
        {"section": "VIP", "price": 5000, "bulk_ticket_id": 1},
        {"section": "General", "price": 3000, "bulk_ticket_id": 2},
        {"section": "Balcony", "price": 2000, "bulk_ticket_id": 3}
    ]
    """
    try:
        prices = TicketService.get_bulk_ticket_prices_by_venue_event(
            session, 
            request_data.venue_id, 
            request_data.event_id
        )
        return prices
    except HTTPException as e:
        raise e

@router.post("/check-in", response_model=TicketCheckInResponse)
def check_in_ticket(
    check_in_data: TicketCheckInRequest,
    session: Session = Depends(get_session)
):
    """Check in a ticket by validating QR data and updating status from SOLD to CHECKEDIN
    
    Request body example:
    {
        "ticket_id": "ticket_70b8b9a0-096f-4f29-ac3a-43f4273e5f81_General:R0:C0",
        "event_id": 1,
        "venue_id": 1,
        "seat": {"section": "General", "row_id": 0, "col_id": 0},
        "firebase_uid": "mznAWfDyWqc67x4OdcpccCUPWub2",
        "order_ref": "ORD-A8A98F28"
    }
    """
    try:
        result = TicketService.check_in_ticket(
            session=session,
            ticket_id_str=check_in_data.ticket_id,
            event_id=check_in_data.event_id,
            venue_id=check_in_data.venue_id,
            seat_dict=check_in_data.seat,
            firebase_uid=check_in_data.firebase_uid,
            order_ref=check_in_data.order_ref
        )
        return result
    except HTTPException as e:
        raise e
