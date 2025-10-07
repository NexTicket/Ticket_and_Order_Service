from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from typing import List, Optional

from database import get_session
from firebase_auth import get_current_user_from_token
from models import (
    LockSeatsRequest, LockSeatsResponse, UnlockSeatsRequest, UnlockSeatsResponse,
    GetLockedSeatsResponse, SeatAvailabilityRequest, SeatAvailabilityResponse,
    ExtendLockRequest, ExtendLockResponse
)
from Order.services.ticket_locking_service import TicketLockingService

router = APIRouter()

@router.post("/lock-seats", response_model=LockSeatsResponse, status_code=status.HTTP_201_CREATED)
def lock_seats(
    request_data: LockSeatsRequest,
    current_user: dict = Depends(get_current_user_from_token),
    session: Session = Depends(get_session)
):
    """
    Lock seats for a verified user in Redis with automatic 5-minute expiration.
    This creates a temporary order that prevents other users from selecting the same seats.
    """
    user_id = current_user['uid']
    return TicketLockingService.lock_seats(session, user_id, request_data)

@router.post("/unlock-seats", response_model=UnlockSeatsResponse)
def unlock_seats(
    request_data: UnlockSeatsRequest,
    current_user: dict = Depends(get_current_user_from_token),
    session: Session = Depends(get_session)
):
    """
    Unlock seats for a user. Can unlock specific seats by order_id/seat_ids or all user's locked seats.
    """
    user_id = current_user['uid']
    return TicketLockingService.unlock_seats(session, user_id, request_data)

@router.get("/locked-seats", response_model=Optional[GetLockedSeatsResponse])
def get_locked_seats(
    current_user: dict = Depends(get_current_user_from_token),
    session: Session = Depends(get_session)
):
    """
    Get currently locked seats for the authenticated user.
    Returns None if no seats are currently locked or if the lock has expired.
    """
    user_id = current_user['uid']
    return TicketLockingService.get_locked_seats(user_id, session)

@router.post("/check-availability", response_model=SeatAvailabilityResponse)
def check_seat_availability(
    request_data: SeatAvailabilityRequest,
    session: Session = Depends(get_session)
):
    """
    Check the availability status of specific seats for an event.
    Returns available, locked, and unavailable (sold) seats.
    """
    return TicketLockingService.check_seat_availability(
        session, request_data.event_id, request_data.seat_ids
    )

@router.post("/extend-lock", response_model=ExtendLockResponse)
def extend_lock(
    request_data: ExtendLockRequest,
    current_user: dict = Depends(get_current_user_from_token)
):
    """
    Extend the lock time for a user's order by additional seconds (default 5 minutes).
    """
    user_id = current_user['uid']
    return TicketLockingService.extend_lock(
        user_id, request_data.order_id, request_data.additional_seconds
    )

@router.delete("/force-unlock/{event_id}/{seat_id}", status_code=status.HTTP_204_NO_CONTENT)
def force_unlock_seat(
    event_id: int,
    seat_id: str,
    current_user: dict = Depends(get_current_user_from_token)
):
    """
    Force unlock a specific seat. Only unlocks seats locked by the current user.
    """
    user_id = current_user['uid']
    unlocked = TicketLockingService._unlock_specific_seats(event_id, [seat_id], user_id)
    if not unlocked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found or not locked by this user"
        )

@router.get("/stats/{event_id}")
def get_locking_stats(
    event_id: int,
    session: Session = Depends(get_session)
):
    """
    Get statistics about seat locking for an event (for debugging/monitoring).
    """
    # This could be expanded to show detailed locking statistics
    from Database.redis_client import redis_conn
    
    # Get all seat locks for this event
    pattern = f"seat_lock:{event_id}:*"
    keys = redis_conn.keys(pattern)
    
    active_locks = []
    expired_locks = 0
    
    for key in keys:
        lock_data = redis_conn.hgetall(key)
        if lock_data:
            from datetime import datetime, timezone
            expires_at = datetime.fromisoformat(lock_data['expires_at'])
            if expires_at > datetime.now(timezone.utc):
                seat_id = key.split(':')[-1]
                active_locks.append({
                    "seat_id": seat_id,
                    "user_id": lock_data['user_id'],
                    "expires_at": expires_at,
                    "order_id": lock_data['order_id']
                })
            else:
                expired_locks += 1
                redis_conn.delete(key)  # Clean up expired lock
    
    return {
        "event_id": event_id,
        "active_locks_count": len(active_locks),
        "expired_locks_cleaned": expired_locks,
        "active_locks": active_locks
    }