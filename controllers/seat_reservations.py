from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging
import json

from models import (
    SeatReservation, SeatReservationCreate, ReservationStatus, UserTicket,
    BulkTicket, CartItem, SeatType
)
from database import get_session
from services.event_venue_client import fetch_event_details
from services.seat_management_service import SeatManagementService
from services.cart_management_service import CartManagementService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/seat-reservations", tags=["seat-reservations"])

class ReserveSeatsRequest:
    def __init__(self, seat_ids: List[str], firebase_uid: str):
        self.seat_ids = seat_ids
        self.firebase_uid = firebase_uid

class ReleaseSeatsRequest:
    def __init__(self, event_id: int, seat_ids: List[str], firebase_uid: str):
        self.event_id = event_id
        self.seat_ids = seat_ids
        self.firebase_uid = firebase_uid

class ConfirmReservationsRequest:
    def __init__(self, firebase_uid: str, order_id: int):
        self.firebase_uid = firebase_uid
        self.order_id = order_id

@router.post("/{event_id}/reserve")
async def reserve_seats(
    event_id: int,
    request_data: dict,
    session: Session = Depends(get_session)
):
    """
    STEP 1: Reserve seats when user selects them on seat map
    Uses consolidated SeatManagementService for efficiency
    """
    try:
        seat_ids = request_data.get("seatIds", [])
        firebase_uid = request_data.get("firebaseUid")
        venue_id = request_data.get("venueId")

        logger.info(f"🎫 STEP 1: Reserving seats for user selection")
        logger.info(f"Event: {event_id}, Seats: {len(seat_ids)}, User: {firebase_uid}")

        if not event_id or not seat_ids or not isinstance(seat_ids, list) or not firebase_uid:
            raise HTTPException(
                status_code=400,
                detail="eventId, seatIds (array), and firebaseUid are required"
            )

        # Use consolidated seat management service
        result = await SeatManagementService.reserve_seats_for_user(
            session=session,
            event_id=event_id,
            seat_ids=seat_ids,
            firebase_uid=firebase_uid,
            venue_id=venue_id
        )

        return {
            "success": True,
            "reservations": result["reservations"],
            "conflicts": result["conflicts"],
            "expires_at": result["expires_at"],
            "message": f"Reserved {len(result['reservations'])} seats, {len(result['conflicts'])} conflicts"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as error:
        logger.error(f"❌ Error in reserve_seats: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reserve seats: {str(error)}"
        )

@router.get("/{event_id}")
async def get_seat_reservations(
    event_id: int,
    firebase_uid: str = None,
    session: Session = Depends(get_session)
):
    """
    Get reservation status for seats in an event
    """
    try:
        logger.info(f"🔍 Getting seat reservations for event: {event_id}")

        # Use consolidated seat management service
        result = SeatManagementService.get_seat_reservations_for_event(
            session=session,
            event_id=event_id,
            firebase_uid=firebase_uid
        )

        return result

    except Exception as error:
        logger.error(f"❌ Error getting reservations: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get reservations: {str(error)}"
        )

@router.post("/release")
async def release_seats(
    request_data: dict,
    session: Session = Depends(get_session)
):
    """
    Release seat reservations (when user deselects seats or cart is cleared)
    """
    try:
        event_id = request_data.get("eventId")
        seat_ids = request_data.get("seatIds", [])
        firebase_uid = request_data.get("firebaseUid")

        logger.info(f"🔓 Releasing seats: event_id={event_id}, seat_ids={seat_ids}, firebase_uid={firebase_uid}")

        if not event_id or not seat_ids or not isinstance(seat_ids, list) or not firebase_uid:
            raise HTTPException(
                status_code=400,
                detail="eventId, seatIds (array), and firebaseUid are required"
            )

        # Use consolidated service to release seats
        cancelled_count = SeatManagementService.release_seats_for_user(
            session=session,
            event_id=event_id,
            seat_ids=seat_ids,
            firebase_uid=firebase_uid
        )

        return {
            "success": True,
            "releasedCount": cancelled_count,
            "message": f"Released {cancelled_count} seat reservations"
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"❌ Error releasing seats: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to release seats: {str(error)}"
        )

@router.post("/{event_id}/confirm")
async def confirm_reservations(
    event_id: int,
    request_data: dict,
    session: Session = Depends(get_session)
):
    """
    Confirm seat reservations (when order is created)
    """
    try:
        firebase_uid = request_data.get("firebaseUid")
        order_id = request_data.get("orderId")

        logger.info(f"✅ Confirming seat reservations: event_id={event_id}, firebase_uid={firebase_uid}, order_id={order_id}")

        if not firebase_uid or not order_id:
            raise HTTPException(
                status_code=400,
                detail="firebaseUid and orderId are required"
            )

        # Use consolidated service to confirm reservations
        confirmed_count = SeatManagementService.confirm_reservations_for_order(
            session=session,
            firebase_uid=firebase_uid,
            order_id=order_id
        )

        return {
            "success": True,
            "confirmedCount": confirmed_count,
            "message": f"Confirmed {confirmed_count} seat reservations"
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"❌ Error confirming reservations: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to confirm reservations: {str(error)}"
        )

@router.post("/cleanup-expired")
async def cleanup_expired_reservations(
    session: Session = Depends(get_session)
):
    """
    Clean up expired reservations - makes seats available again
    """
    try:
        logger.info("🧹 Cleaning up expired reservations...")

        # Use consolidated service for cleanup
        cleaned_count = SeatManagementService.release_expired_reservations(session)

        return {
            "success": True,
            "expiredCount": cleaned_count,
            "message": f"Cleaned up {cleaned_count} expired reservations"
        }

    except Exception as error:
        logger.error(f"❌ Error cleaning up reservations: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cleanup reservations: {str(error)}"
        )

@router.post("/cart/add")
async def add_to_cart_from_reservations(
    request_data: dict,
    session: Session = Depends(get_session)
):
    """
    STEP 2: Add reserved seats to cart - creates actual cart items
    This happens when user clicks "Add to Cart" after selecting seats
    """
    try:
        firebase_uid = request_data.get("firebaseUid")
        event_id = request_data.get("eventId")
        venue_id = request_data.get("venueId")
        seats_data = request_data.get("seats", [])
        
        logger.info(f"🛒 STEP 2: Adding reserved seats to cart")
        logger.info(f"User: {firebase_uid}, Event: {event_id}, Seats: {len(seats_data)}")
        
        if not firebase_uid or not event_id or not seats_data:
            raise HTTPException(
                status_code=400,
                detail="firebaseUid, eventId, and seats data are required"
            )
        
        # Extract seat IDs for reservation validation
        seat_ids = [seat["seatId"] for seat in seats_data]
        
        # First ensure seats are reserved
        reservation_result = await SeatManagementService.reserve_seats_for_user(
            session=session,
            event_id=event_id,
            seat_ids=seat_ids,
            firebase_uid=firebase_uid,
            venue_id=venue_id
        )
        
        if reservation_result["conflicts"]:
            raise HTTPException(
                status_code=409,
                detail=f"Some seats unavailable: {reservation_result['conflicts']}"
            )
        
        # Use venue_id from reservation result or fallback
        final_venue_id = venue_id or reservation_result.get("venue_id", 1)
        
        # Add to cart using consolidated service
        cart_result = await CartManagementService.add_reserved_seats_to_cart(
            session=session,
            firebase_uid=firebase_uid,
            event_id=event_id,
            venue_id=final_venue_id,
            seats_data=seats_data
        )
        
        logger.info(f"✅ STEP 2 Complete: {cart_result['total_items']} seats added to cart")
        
        return {
            "success": True,
            **cart_result,
            "message": f"Added {cart_result['total_items']} seats to cart"
        }
        
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"❌ Error adding to cart: {error}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add to cart: {str(error)}"
        )