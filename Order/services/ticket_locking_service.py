import json
import uuid
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from sqlmodel import Session, select

from Database.redis_client import redis_conn, CART_EXPIRATION_SECONDS as ORDER_EXPIRATION_SECONDS
from models import (
    BulkTicket, UserTicket, UserOrder, UserOrderCreate,
    LockSeatsRequest, LockSeatsResponse, UnlockSeatsRequest, UnlockSeatsResponse,
    GetLockedSeatsResponse, SeatAvailabilityResponse, ExtendLockResponse, OrderStatus,
    SeatOrder, SeatOrderCreate
)
from Payment.services.stripe_service import StripeService

class TicketLockingService:
    
    @staticmethod
    async def lock_seats(session: Session, user_id: str, request_data: LockSeatsRequest) -> LockSeatsResponse:
        """
        Lock seats for a user in Redis with automatic expiration.
        Creates a payment intent and updates the order record.
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
        TicketLockingService._cleanup_user_locks(user_id, session)
        
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
        
        # 5. Create new order and lock seats
        order_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ORDER_EXPIRATION_SECONDS)
        
        # Calculate total amount
        total_amount = 0
        seat_assignments = {}  # bulk_ticket_id -> [seat_ids]
        
        # Match seats to bulk tickets based on seat prefix
        if request_data.bulk_ticket_id:
            # If bulk_ticket_id is provided, use that for all seats
            bulk_ticket = session.get(BulkTicket, request_data.bulk_ticket_id)
            if bulk_ticket:
                total_amount = bulk_ticket.price * len(request_data.seat_ids)
                seat_assignments[str(bulk_ticket.id)] = request_data.seat_ids
        else:
            # Otherwise, try to match each seat to a bulk ticket based on seat prefix
            bulk_tickets = session.exec(
                select(BulkTicket).where(BulkTicket.event_id == request_data.event_id)
            ).all()
            
            for seat_id in request_data.seat_ids:
                matched = False
                for bulk_ticket in bulk_tickets:
                    if seat_id.startswith(bulk_ticket.seat_prefix):
                        if str(bulk_ticket.id) not in seat_assignments:
                            seat_assignments[str(bulk_ticket.id)] = []
                        seat_assignments[str(bulk_ticket.id)].append(seat_id)
                        total_amount += bulk_ticket.price
                        matched = True
                        break
                
                if not matched:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Seat {seat_id} does not match any available ticket types"
                    )
        
        # 6. First, lock seats in Redis (which could fail)
        redis_key = f"order:{user_id}"
        order_data_redis = {
            "order_id": order_id,
            "user_id": user_id,
            "event_id": request_data.event_id,
            "seat_ids": json.dumps(request_data.seat_ids),
            "bulk_ticket_info": json.dumps(bulk_ticket_info),
            "status": "locked",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat()
        }
        
        try:
            pipe = redis_conn.pipeline()
            
            # Store the main order data
            pipe.hset(redis_key, mapping=order_data_redis)
            pipe.expire(redis_key, ORDER_EXPIRATION_SECONDS)
            
            # Store individual seat locks for conflict checking
            for seat_id in request_data.seat_ids:
                seat_lock_key = f"seat_lock:{request_data.event_id}:{seat_id}"
                seat_lock_data = {
                    "user_id": user_id,
                    "order_id": order_id,
                    "locked_at": datetime.now(timezone.utc).isoformat(),
                    "expires_at": expires_at.isoformat()
                }
                pipe.hset(seat_lock_key, mapping=seat_lock_data)
                pipe.expire(seat_lock_key, ORDER_EXPIRATION_SECONDS)
            
            pipe.execute()
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not lock seats in Redis: {e}"
            )
            
        # 7. Now create permanent order in database after Redis locks were successful
        try:
            # Create pending order in database
            order_data_db = UserOrderCreate(
                firebase_uid=user_id,
                total_amount=total_amount,
                status=OrderStatus.PENDING
            )
            
            db_order = UserOrder.model_validate(order_data_db)
            db_order.id = order_id  # Use the same order_id for Redis and database
            db_order.notes = json.dumps({
                "seat_assignments": seat_assignments,
                "order_id": order_id
            })
            session.add(db_order)
            # Commit the order first to ensure it exists for foreign key references
            session.commit()
            session.refresh(db_order)
            
            # Create OrderSeatAssignment records for each bulk ticket
            try:
                for bulk_ticket_id, seats in seat_assignments.items():
                    bulk_ticket = session.get(BulkTicket, int(bulk_ticket_id))
                    if bulk_ticket:
                        seat_assignment = SeatOrder(
                        order_id=order_id,
                        event_id=request_data.event_id,
                        venue_id=bulk_ticket.venue_id,
                        bulk_ticket_id=bulk_ticket.id,
                        seat_ids=json.dumps(seats)
                    )
                        session.add(seat_assignment)
                session.commit()
            except Exception as e:
                print(f"Warning: Failed to create seat assignments: {e}")
            
            # Create payment intent with Stripe and update order
            payment_intent_id = None
            try:
                # Get the order
                db_order = session.get(UserOrder, order_id)
                if db_order and db_order.status == OrderStatus.PENDING:
                    # Stripe expects amounts in cents (smallest currency unit)
                    # For LKR, multiply by 100 to convert from rupees to cents
                    stripe_amount = int(total_amount * 100)  
                    
                    # Add debugging info
                    print(f"Creating payment intent: Original amount: {total_amount} LKR, Stripe amount: {stripe_amount} cents")
                    
                    # Create Stripe payment intent directly
                    payment_data = await StripeService.create_payment_intent(
                        amount=stripe_amount, 
                        order_id=order_id,
                        user_id=user_id
                    )
                    
                    # Debug payment data
                    print(f"Payment data: {payment_data}")
                    
                    # Update order with payment intent ID
                    if 'payment_intent_id' in payment_data:
                        payment_intent_id = payment_data['payment_intent_id']
                        db_order.payment_intent_id = payment_intent_id
                        db_order.updated_at = datetime.now(timezone.utc)
                        session.add(db_order)
                        session.commit()
                        session.refresh(db_order)
                        print(f"Updated order with payment_intent_id: {payment_intent_id}")
                    else:
                        print(f"Error: 'payment_intent_id' not found in payment data: {payment_data}")
                
            except Exception as e:

                print(f"Warning: Failed to create payment intent: {str(e)}")
                
        except Exception as e:
            # If database update fails, clean up Redis locks
            try:
                # Clean up Redis locks since database update failed
                pipe = redis_conn.pipeline()
                pipe.delete(redis_key)
                for seat_id in request_data.seat_ids:
                    pipe.delete(f"seat_lock:{request_data.event_id}:{seat_id}")
                pipe.execute()
            except:
                pass  
                
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create order in database: {e}"
            )
        
        db_order = session.get(UserOrder, order_id)
        
        message = "Order created successfully. Your selection will expire in 5 minutes."
        if payment_intent_id:
            message += " Payment intent created."
            
        response = LockSeatsResponse(
            message=message,
            order_id=order_id,
            user_id=user_id,
            seat_ids=request_data.seat_ids,
            event_id=request_data.event_id,
            expires_in_seconds=ORDER_EXPIRATION_SECONDS,
            expires_at=expires_at
        )
        
        client_secret = payment_data['client_secret']

        if payment_intent_id and client_secret:
            response.payment_intent_id = payment_intent_id
            response.client_secret = client_secret
        elif db_order and db_order.payment_intent_id:
            response.payment_intent_id = db_order.payment_intent_id
            
        return response
    
    @staticmethod
    def unlock_seats(session: Session, user_id: str, request_data: UnlockSeatsRequest) -> UnlockSeatsResponse:
        """
        Unlock specific seats or all seats for a user.
        """
        try:
            if request_data.order_id:
                # Unlock specific order
                order_data = TicketLockingService._get_user_order_data(user_id)
                if not order_data or order_data.get('order_id') != request_data.order_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Order not found or doesn't belong to user"
                    )
                
                seat_ids = json.loads(order_data.get('seat_ids', '[]'))
                event_id = order_data.get('event_id')
                order_id = order_data.get('order_id')
                
                # If specific seats provided, unlock only those
                if request_data.seat_ids:
                    seats_to_unlock = [sid for sid in request_data.seat_ids if sid in seat_ids]
                else:
                    seats_to_unlock = seat_ids
                
                TicketLockingService._unlock_specific_seats(event_id, seats_to_unlock, user_id)
                
                # Update order data if partially unlocking
                if request_data.seat_ids and len(seats_to_unlock) < len(seat_ids):
                    remaining_seats = [sid for sid in seat_ids if sid not in seats_to_unlock]
                    order_data['seat_ids'] = json.dumps(remaining_seats)
                    redis_conn.hset(f"order:{user_id}", mapping=order_data)
                else:
                    # Remove entire order if all seats unlocked
                    redis_conn.delete(f"order:{user_id}")
                    
                # Cancel order in database (if it exists)
                order = session.get(UserOrder, order_id)
                if order and order.status == OrderStatus.PENDING:
                    order.status = OrderStatus.CANCELLED
                    order.notes = json.dumps({
                        "cancellation_reason": "User unlocked seats",
                        "cancelled_at": datetime.now(timezone.utc).isoformat()
                    })
                    session.add(order)
                    
                    # We don't need to delete seat assignments when cancelling
                    # They're useful to keep for reference even for cancelled orders
                    
                    session.commit()
                
                return UnlockSeatsResponse(
                    message=f"Successfully unlocked {len(seats_to_unlock)} seats",
                    unlocked_seat_ids=seats_to_unlock
                )
            
            else:
                # Unlock all seats for user
                order_data = TicketLockingService._get_user_order_data(user_id)
                if order_data and order_data.get('order_id'):
                    order_id = order_data.get('order_id')
                    # Cancel order in database (if it exists)
                    order = session.get(UserOrder, order_id)
                    if order and order.status == OrderStatus.PENDING:
                        order.status = OrderStatus.CANCELLED
                        order.notes = json.dumps({
                            "cancellation_reason": "User unlocked all seats",
                            "cancelled_at": datetime.now(timezone.utc).isoformat()
                        })
                        session.add(order)
                        session.commit()
                
                unlocked_seats = TicketLockingService._cleanup_user_locks(user_id, session)
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
    def get_locked_seats(user_id: str, session: Session) -> Optional[GetLockedSeatsResponse]:
        """
        Get current locked seats for a user.
        """
        order_data = TicketLockingService._get_user_order_data(user_id)
        
        if not order_data:
            return None
        
        expires_at = datetime.fromisoformat(order_data['expires_at'])
        remaining_seconds = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
        
        if remaining_seconds <= 0:
            # Clean up expired order and cancel order
            TicketLockingService._cleanup_user_locks(user_id, session)
            return None
        
        # Parse bulk ticket information if available
        bulk_ticket_info = {}
        if 'bulk_ticket_info' in order_data:
            bulk_ticket_info = json.loads(order_data['bulk_ticket_info'])
        
        return GetLockedSeatsResponse(
            order_id=order_data['order_id'],
            user_id=order_data['user_id'],
            seat_ids=json.loads(order_data['seat_ids']),
            event_id=int(order_data['event_id']),
            status=order_data['status'],
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
    def extend_lock(user_id: str, order_id: str, additional_seconds: int = 300) -> ExtendLockResponse:
        """
        Extend the lock time for a user's order.
        """
        order_data = TicketLockingService._get_user_order_data(user_id)
        
        if not order_data or order_data.get('order_id') != order_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found or doesn't belong to user"
            )
        
        current_expires = datetime.fromisoformat(order_data['expires_at'])
        new_expires = current_expires + timedelta(seconds=additional_seconds)
        
        # Update order expiration
        order_data['expires_at'] = new_expires.isoformat()
        
        try:
            pipe = redis_conn.pipeline()
            
            # Update main order
            pipe.hset(f"order:{user_id}", mapping=order_data)
            pipe.expire(f"order:{user_id}", int((new_expires - datetime.now(timezone.utc)).total_seconds()))
            
            # Update individual seat locks
            seat_ids = json.loads(order_data['seat_ids'])
            event_id = order_data['event_id']
            
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
            order_id=order_id,
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
    def _cleanup_user_locks(user_id: str, session: Optional[Session] = None) -> List[str]:
        """
        Clean up all existing locks for a user.
        """
        unlocked_seats = []
        
        # Get user's current order
        order_data = TicketLockingService._get_user_order_data(user_id)
        
        if order_data:
            seat_ids = json.loads(order_data.get('seat_ids', '[]'))
            event_id = order_data.get('event_id')
            order_id = order_data.get('order_id')
            
            unlocked_seats = TicketLockingService._unlock_specific_seats(event_id, seat_ids, user_id)
            
            # Remove user's order
            redis_conn.delete(f"order:{user_id}")
            
            # Cancel order in database if session is provided
            if session and order_id:
                order = session.get(UserOrder, order_id)
                if order and order.status == OrderStatus.PENDING:
                    order.status = OrderStatus.CANCELLED
                    order.notes = json.dumps({
                        "cancellation_reason": "Cleanup or expiration",
                        "cancelled_at": datetime.now(timezone.utc).isoformat()
                    })
                    session.add(order)
                    
                    # We don't need to delete seat assignments when cancelling
                    # They're useful to keep for reference even for cancelled orders
                    
                    session.commit()
        
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
    def _get_user_order_data(user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user's current order data from Redis.
        """
        # Check both new "order:" prefix and legacy "cart:" prefix for backward compatibility
        order_data = redis_conn.hgetall(f"order:{user_id}")
        if order_data:
            return order_data
            
        # Fall back to old cart format for compatibility during transition
        legacy_data = redis_conn.hgetall(f"cart:{user_id}")
        return legacy_data if legacy_data else None