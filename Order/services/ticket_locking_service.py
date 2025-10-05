import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from sqlmodel import Session, select

from Database.redis_client import redis_conn, CART_EXPIRATION_SECONDS
from models import (
    BulkTicket, UserTicket,
    LockSeatsRequest, LockSeatsResponse, UnlockSeatsRequest, UnlockSeatsResponse,
    GetLockedSeatsResponse, SeatAvailabilityResponse, ExtendLockResponse
)

class TicketLockingService:
    
    @staticmethod
    def lock_seats(session: Session, user_id: str, request_data: LockSeatsRequest) -> LockSeatsResponse:
        """
        Lock seats for a user in Redis with automatic expiration.
        """
        # 1. Validate that the event exists and seats are potentially available
        TicketLockingService._validate_seat_availability(session, request_data.event_id, request_data.seat_ids)
        
        # 2. Check if any of these seats are already locked by other users
        conflicted_seats = TicketLockingService._check_seat_conflicts(request_data.event_id, request_data.seat_ids, user_id)
        if conflicted_seats:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Seats already locked by other users: {conflicted_seats}"
            )
        
        # 3. Release any existing locks for this user (cleanup)
        TicketLockingService._cleanup_user_locks(user_id)
        
        # 4. Get bulk ticket info for pricing
        bulk_ticket_info = {}
        if request_data.bulk_ticket_id:
            bulk_ticket = session.get(BulkTicket, request_data.bulk_ticket_id)
            if bulk_ticket:
                bulk_ticket_info = {
                    "bulk_ticket_id": bulk_ticket.id,
                    "price_per_seat": bulk_ticket.price,
                    "seat_type": bulk_ticket.seat_type
                }
        
        # 5. Create new cart and lock seats
        cart_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=CART_EXPIRATION_SECONDS)
        
        redis_key = f"cart:{user_id}"
        cart_data = {
            "cart_id": cart_id,
            "user_id": user_id,
            "event_id": request_data.event_id,
            "seat_ids": json.dumps(request_data.seat_ids),
            "bulk_ticket_info": json.dumps(bulk_ticket_info),
            "status": "locked",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat()
        }
        
        # 6. Store in Redis with expiration
        try:
            pipe = redis_conn.pipeline()
            
            # Store the main cart data
            pipe.hset(redis_key, mapping=cart_data)
            pipe.expire(redis_key, CART_EXPIRATION_SECONDS)
            
            # Store individual seat locks for conflict checking
            for seat_id in request_data.seat_ids:
                seat_lock_key = f"seat_lock:{request_data.event_id}:{seat_id}"
                seat_lock_data = {
                    "user_id": user_id,
                    "cart_id": cart_id,
                    "locked_at": datetime.now(timezone.utc).isoformat(),
                    "expires_at": expires_at.isoformat()
                }
                pipe.hset(seat_lock_key, mapping=seat_lock_data)
                pipe.expire(seat_lock_key, CART_EXPIRATION_SECONDS)
            
            pipe.execute()
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not lock seats in Redis: {e}"
            )
        
        return LockSeatsResponse(
            message="Seats locked successfully. Your selection will expire in 5 minutes.",
            cart_id=cart_id,
            user_id=user_id,
            seat_ids=request_data.seat_ids,
            event_id=request_data.event_id,
            expires_in_seconds=CART_EXPIRATION_SECONDS,
            expires_at=expires_at
        )
    
    @staticmethod
    def unlock_seats(user_id: str, request_data: UnlockSeatsRequest) -> UnlockSeatsResponse:
        """
        Unlock specific seats or all seats for a user.
        """
        try:
            if request_data.cart_id:
                # Unlock specific cart
                cart_data = TicketLockingService._get_user_cart_data(user_id)
                if not cart_data or cart_data.get('cart_id') != request_data.cart_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Cart not found or doesn't belong to user"
                    )
                
                seat_ids = json.loads(cart_data.get('seat_ids', '[]'))
                event_id = cart_data.get('event_id')
                
                # If specific seats provided, unlock only those
                if request_data.seat_ids:
                    seats_to_unlock = [sid for sid in request_data.seat_ids if sid in seat_ids]
                else:
                    seats_to_unlock = seat_ids
                
                TicketLockingService._unlock_specific_seats(event_id, seats_to_unlock, user_id)
                
                # Update cart data if partially unlocking
                if request_data.seat_ids and len(seats_to_unlock) < len(seat_ids):
                    remaining_seats = [sid for sid in seat_ids if sid not in seats_to_unlock]
                    cart_data['seat_ids'] = json.dumps(remaining_seats)
                    redis_conn.hset(f"cart:{user_id}", mapping=cart_data)
                else:
                    # Remove entire cart if all seats unlocked
                    redis_conn.delete(f"cart:{user_id}")
                
                return UnlockSeatsResponse(
                    message=f"Successfully unlocked {len(seats_to_unlock)} seats",
                    unlocked_seat_ids=seats_to_unlock
                )
            
            else:
                # Unlock all seats for user
                unlocked_seats = TicketLockingService._cleanup_user_locks(user_id)
                return UnlockSeatsResponse(
                    message=f"Successfully unlocked all seats for user",
                    unlocked_seat_ids=unlocked_seats
                )
                
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not unlock seats: {e}"
            )
    
    @staticmethod
    def get_locked_seats(user_id: str) -> Optional[GetLockedSeatsResponse]:
        """
        Get current locked seats for a user.
        """
        cart_data = TicketLockingService._get_user_cart_data(user_id)
        
        if not cart_data:
            return None
        
        expires_at = datetime.fromisoformat(cart_data['expires_at'])
        remaining_seconds = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
        
        if remaining_seconds <= 0:
            # Clean up expired cart
            TicketLockingService._cleanup_user_locks(user_id)
            return None
        
        # Parse bulk ticket information if available
        bulk_ticket_info = {}
        if 'bulk_ticket_info' in cart_data:
            bulk_ticket_info = json.loads(cart_data['bulk_ticket_info'])
        
        return GetLockedSeatsResponse(
            cart_id=cart_data['cart_id'],
            user_id=cart_data['user_id'],
            seat_ids=json.loads(cart_data['seat_ids']),
            event_id=int(cart_data['event_id']),
            status=cart_data['status'],
            expires_at=expires_at,
            remaining_seconds=remaining_seconds,
            bulk_ticket_info=bulk_ticket_info
        )
    
    @staticmethod
    def check_seat_availability(session: Session, event_id: int, seat_ids: List[str]) -> SeatAvailabilityResponse:
        """
        Check availability status of specific seats for an event.
        """
        # Check what's sold/reserved in main database
        stmt = select(UserTicket).where(
            UserTicket.seat_id.in_(seat_ids)
        ).join(BulkTicket).where(
            BulkTicket.event_id == event_id
        )
        sold_tickets = session.exec(stmt).all()
        unavailable_seats = [ticket.seat_id for ticket in sold_tickets]
        
        # Check what's currently locked in Redis
        locked_seats = []
        available_seats = []
        
        for seat_id in seat_ids:
            if seat_id in unavailable_seats:
                continue
                
            seat_lock_key = f"seat_lock:{event_id}:{seat_id}"
            lock_data = redis_conn.hgetall(seat_lock_key)
            
            if lock_data:
                expires_at = datetime.fromisoformat(lock_data['expires_at'])
                if expires_at > datetime.now(timezone.utc):
                    locked_seats.append({
                        "seat_id": seat_id,
                        "locked_by_user_id": lock_data['user_id'],
                        "expires_at": expires_at
                    })
                else:
                    # Clean up expired lock
                    redis_conn.delete(seat_lock_key)
                    available_seats.append(seat_id)
            else:
                available_seats.append(seat_id)
        
        return SeatAvailabilityResponse(
            event_id=event_id,
            available_seats=available_seats,
            locked_seats=locked_seats,
            unavailable_seats=unavailable_seats
        )
    
    @staticmethod
    def extend_lock(user_id: str, cart_id: str, additional_seconds: int = 300) -> ExtendLockResponse:
        """
        Extend the lock time for a user's cart.
        """
        cart_data = TicketLockingService._get_user_cart_data(user_id)
        
        if not cart_data or cart_data.get('cart_id') != cart_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cart not found or doesn't belong to user"
            )
        
        current_expires = datetime.fromisoformat(cart_data['expires_at'])
        new_expires = current_expires + timedelta(seconds=additional_seconds)
        
        # Update cart expiration
        cart_data['expires_at'] = new_expires.isoformat()
        
        try:
            pipe = redis_conn.pipeline()
            
            # Update main cart
            pipe.hset(f"cart:{user_id}", mapping=cart_data)
            pipe.expire(f"cart:{user_id}", int((new_expires - datetime.now(timezone.utc)).total_seconds()))
            
            # Update individual seat locks
            seat_ids = json.loads(cart_data['seat_ids'])
            event_id = cart_data['event_id']
            
            for seat_id in seat_ids:
                seat_lock_key = f"seat_lock:{event_id}:{seat_id}"
                lock_data = redis_conn.hgetall(seat_lock_key)
                if lock_data:
                    lock_data['expires_at'] = new_expires.isoformat()
                    pipe.hset(seat_lock_key, mapping=lock_data)
                    pipe.expire(seat_lock_key, int((new_expires - datetime.now(timezone.utc)).total_seconds()))
            
            pipe.execute()
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not extend lock: {e}"
            )
        
        remaining_seconds = int((new_expires - datetime.now(timezone.utc)).total_seconds())
        
        return ExtendLockResponse(
            message="Lock extended successfully",
            cart_id=cart_id,
            new_expires_at=new_expires,
            total_remaining_seconds=remaining_seconds
        )
    
    # --- Helper Methods ---
    
    @staticmethod
    def _validate_seat_availability(session: Session, event_id: int, seat_ids: List[str]):
        """
        Validate that the event exists and seats are not already sold.
        """
        # Check if seats are already sold in the main database
        stmt = select(UserTicket).where(
            UserTicket.seat_id.in_(seat_ids)
        ).join(BulkTicket).where(
            BulkTicket.event_id == event_id
        )
        sold_tickets = session.exec(stmt).all()
        
        if sold_tickets:
            sold_seat_ids = [ticket.seat_id for ticket in sold_tickets]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Seats already sold: {sold_seat_ids}"
            )
    
    @staticmethod
    def _check_seat_conflicts(event_id: int, seat_ids: List[str], user_id: str) -> List[str]:
        """
        Check if any seats are already locked by other users.
        """
        conflicted_seats = []
        
        for seat_id in seat_ids:
            seat_lock_key = f"seat_lock:{event_id}:{seat_id}"
            lock_data = redis_conn.hgetall(seat_lock_key)
            
            if lock_data and lock_data.get('user_id') != user_id:
                # Check if lock is still valid
                expires_at = datetime.fromisoformat(lock_data['expires_at'])
                if expires_at > datetime.now(timezone.utc):
                    conflicted_seats.append(seat_id)
                else:
                    # Clean up expired lock
                    redis_conn.delete(seat_lock_key)
        
        return conflicted_seats
    
    @staticmethod
    def _cleanup_user_locks(user_id: str) -> List[str]:
        """
        Clean up all existing locks for a user.
        """
        unlocked_seats = []
        
        # Get user's current cart
        cart_data = TicketLockingService._get_user_cart_data(user_id)
        
        if cart_data:
            seat_ids = json.loads(cart_data.get('seat_ids', '[]'))
            event_id = cart_data.get('event_id')
            
            unlocked_seats = TicketLockingService._unlock_specific_seats(event_id, seat_ids, user_id)
            
            # Remove user's cart
            redis_conn.delete(f"cart:{user_id}")
        
        return unlocked_seats
    
    @staticmethod
    def _unlock_specific_seats(event_id: int, seat_ids: List[str], user_id: str) -> List[str]:
        """
        Unlock specific seats for an event.
        """
        unlocked_seats = []
        
        for seat_id in seat_ids:
            seat_lock_key = f"seat_lock:{event_id}:{seat_id}"
            lock_data = redis_conn.hgetall(seat_lock_key)
            
            # Only unlock if it belongs to this user
            if lock_data and lock_data.get('user_id') == user_id:
                redis_conn.delete(seat_lock_key)
                unlocked_seats.append(seat_id)
        
        return unlocked_seats
    
    @staticmethod
    def _get_user_cart_data(user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user's current cart data from Redis.
        """
        cart_data = redis_conn.hgetall(f"cart:{user_id}")
        return cart_data if cart_data else None