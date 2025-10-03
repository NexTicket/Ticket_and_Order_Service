from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
from models import (
    UserOrder, UserOrderCreate, UserOrderRead, UserOrderUpdate,
    UserTicket, Transaction, TransactionCreate,
    BulkTicket, OrderStatus, TransactionStatus,
    RedisCartItem, OrderSummaryResponse
)
from Ticket.services.ticket_service import TicketService
from Order.services.ticket_locking_service import TicketLockingService
from Payment.services.stripe_service import StripeService
from Database.redis_client import redis_conn

class OrderService:
    
    @staticmethod
    def get_redis_cart_summary(firebase_uid: str) -> Optional[OrderSummaryResponse]:
        """Get cart summary from Redis"""
        cart_data = TicketLockingService._get_user_cart_data(firebase_uid)
        
        if not cart_data:
            return None
        
        # Parse cart data
        seat_ids = json.loads(cart_data.get('seat_ids', '[]'))
        event_id = int(cart_data.get('event_id'))
        expires_at = datetime.fromisoformat(cart_data['expires_at'])
        remaining_seconds = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
        
        if remaining_seconds <= 0:
            return None
        
        # Get bulk ticket info if available
        bulk_ticket_info = {}
        if cart_data.get('bulk_ticket_info'):
            try:
                bulk_ticket_info = json.loads(cart_data['bulk_ticket_info'])
            except json.JSONDecodeError:
                bulk_ticket_info = {}
        
        # Calculate pricing
        price_per_seat = bulk_ticket_info.get('price_per_seat', 0.0)
        total_amount = price_per_seat * len(seat_ids)
        
        items = [RedisCartItem(
            bulk_ticket_id=bulk_ticket_info.get('bulk_ticket_id', 0),
            seat_ids=seat_ids,
            quantity=len(seat_ids),
            price_per_seat=price_per_seat
        )]
        
        return OrderSummaryResponse(
            cart_id=cart_data['cart_id'],
            user_id=firebase_uid,
            total_seats=len(seat_ids),
            total_amount=total_amount,
            items=items,
            expires_at=expires_at,
            remaining_seconds=remaining_seconds
        )
    
    @staticmethod
    def create_order_from_redis_cart(session: Session, firebase_uid: str, payment_method: str) -> UserOrder:
        """Create order from Redis temporary cart"""
        # Get cart data from Redis
        cart_data = TicketLockingService._get_user_cart_data(firebase_uid)
        if not cart_data:
            raise HTTPException(status_code=400, detail="No temporary cart found or cart expired")
        
        # Parse cart data
        seat_ids = json.loads(cart_data.get('seat_ids', '[]'))
        event_id = int(cart_data.get('event_id'))
        
        if not seat_ids:
            raise HTTPException(status_code=400, detail="No seats in cart")
        
        # Get bulk ticket information to calculate pricing
        # For now, we'll need to determine which bulk ticket these seats belong to
        # This requires matching seat_ids to bulk_ticket based on seat_prefix and event_id
        bulk_tickets = session.exec(
            select(BulkTicket).where(BulkTicket.event_id == event_id)
        ).all()
        
        if not bulk_tickets:
            raise HTTPException(status_code=404, detail="No tickets available for this event")
        
        # Match seats to bulk tickets based on seat prefix
        total_amount = 0
        seat_assignments = {}  # bulk_ticket_id -> [seat_ids]
        
        for seat_id in seat_ids:
            matched = False
            for bulk_ticket in bulk_tickets:
                if seat_id.startswith(bulk_ticket.seat_prefix):
                    if bulk_ticket.id not in seat_assignments:
                        seat_assignments[bulk_ticket.id] = []
                    seat_assignments[bulk_ticket.id].append(seat_id)
                    total_amount += bulk_ticket.price
                    matched = True
                    break
            
            if not matched:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Seat {seat_id} does not match any available ticket types"
                )
        
        # Create order
        order_data = UserOrderCreate(
            firebase_uid=firebase_uid,
            total_amount=total_amount,
            status=OrderStatus.PENDING
        )
        
        db_order = UserOrder.model_validate(order_data)
        session.add(db_order)
        session.commit()
        session.refresh(db_order)
        
        # Create transaction
        transaction_data = TransactionCreate(
            order_id=db_order.id,
            amount=total_amount,
            payment_method=payment_method,
            status=TransactionStatus.PENDING
        )
        
        db_transaction = Transaction.model_validate(transaction_data)
        session.add(db_transaction)
        session.commit()
        
        # Store seat assignments in order for later completion
        # We'll store this as a note for now, but ideally this should be in a separate table
        db_order.notes = json.dumps({
            "seat_assignments": seat_assignments,
            "cart_id": cart_data['cart_id']
        })
        session.add(db_order)
        session.commit()
        session.refresh(db_order)
        
        return db_order
    
    @staticmethod
    async def complete_order(session: Session, order_id: int, payment_intent_id: str, firebase_uid: str) -> UserOrder:
        """Complete order from Redis cart data"""
        order = session.get(UserOrder, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.status != OrderStatus.PENDING:
            raise HTTPException(status_code=400, detail="Order is not in pending status")
        
        # Verify payment intent ID matches
        if order.payment_intent_id != payment_intent_id:
            raise HTTPException(status_code=400, detail="Payment intent ID mismatch")
        
        # Verify payment with Stripe
        is_payment_successful = await StripeService.verify_payment_success(payment_intent_id)
        if not is_payment_successful:
            raise HTTPException(status_code=400, detail="Payment not successful")
        
        # Get seat assignments from order notes
        if not order.notes:
            raise HTTPException(status_code=400, detail="No seat assignment data found in order")
        
        try:
            order_data = json.loads(order.notes)
            seat_assignments = order_data.get("seat_assignments", {})
            cart_id = order_data.get("cart_id")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid order data format")
        
        if not seat_assignments:
            raise HTTPException(status_code=400, detail="No seat assignments found")
        
        # Create user tickets from seat assignments
        user_tickets = []
        for bulk_ticket_id, seat_ids in seat_assignments.items():
            bulk_ticket = session.get(BulkTicket, int(bulk_ticket_id))
            if not bulk_ticket:
                raise HTTPException(status_code=404, detail=f"Bulk ticket {bulk_ticket_id} not found")
            
            for seat_id in seat_ids:
                # Create individual user ticket
                user_ticket = UserTicket(
                    order_id=order.id,
                    bulk_ticket_id=bulk_ticket.id,
                    firebase_uid=order.firebase_uid,
                    seat_id=seat_id,
                    price_paid=bulk_ticket.price,
                    status="sold"
                )
                
                # Generate QR code data
                qr_data = {
                    "ticket_id": f"temp_{order.id}_{seat_id}",
                    "event_id": bulk_ticket.event_id,
                    "venue_id": bulk_ticket.venue_id,
                    "seat_id": seat_id,
                    "firebase_uid": order.firebase_uid,
                    "order_ref": order.order_reference
                }
                user_ticket.qr_code_data = json.dumps(qr_data)
                
                session.add(user_ticket)
                user_tickets.append(user_ticket)
                
                # Decrease available seats
                bulk_ticket.available_seats -= 1
                session.add(bulk_ticket)
        
        # Update order with completion details
        order.status = OrderStatus.COMPLETED
        order.stripe_payment_id = payment_intent_id
        order.completed_at = datetime.now(timezone.utc)
        order.updated_at = datetime.now(timezone.utc)
        session.add(order)
        
        # Update transaction status
        transaction = session.exec(
            select(Transaction).where(Transaction.order_id == order_id)
        ).first()
        if transaction:
            transaction.status = TransactionStatus.SUCCESS
            transaction.transaction_reference = payment_intent_id
            session.add(transaction)
        
        # Clear Redis cart
        TicketLockingService._cleanup_user_locks(firebase_uid)
        
        session.commit()
        session.refresh(order)
        
        return order
    
    @staticmethod
    def cancel_order(session: Session, order_id: int) -> UserOrder:
        """Cancel an order"""
        order = session.get(UserOrder, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.status not in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
            raise HTTPException(status_code=400, detail="Cannot cancel this order")
        
        order.status = OrderStatus.CANCELLED
        session.add(order)
        
        # Update transaction status
        transaction = session.exec(
            select(Transaction).where(Transaction.order_id == order_id)
        ).first()
        if transaction:
            transaction.status = TransactionStatus.FAILED
            session.add(transaction)
        
        session.commit()
        session.refresh(order)
        
        return order
    
    @staticmethod
    def get_order(session: Session, order_id: int) -> Optional[UserOrder]:
        """Get order by ID"""
        return session.get(UserOrder, order_id)
    
    @staticmethod
    def get_user_orders(session: Session, firebase_uid: str) -> List[UserOrder]:
        """Get all orders for a user by Firebase UID"""
        statement = select(UserOrder).where(UserOrder.firebase_uid == firebase_uid)
        return session.exec(statement).all()
    
    @staticmethod
    def get_order_tickets(session: Session, order_id: int) -> List[UserTicket]:
        """Get all tickets for an order"""
        statement = select(UserTicket).where(UserTicket.order_id == order_id)
        return session.exec(statement).all()
    
    @staticmethod
    def get_order_with_details(session: Session, order_id: int) -> dict:
        """Get order with complete details including tickets"""
        order = session.get(UserOrder, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        tickets = OrderService.get_order_tickets(session, order_id)
        
        transactions = session.exec(
            select(Transaction).where(Transaction.order_id == order_id)
        ).all()
        
        return {
            "order": order,
            "tickets": tickets,
            "transactions": transactions
        }
    

    
    @staticmethod
    async def create_payment_intent(session: Session, order_id: int, amount: int):
        """Create payment intent and update order"""
        order = OrderService.get_order(session, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.status != OrderStatus.PENDING:
            raise HTTPException(status_code=400, detail="Order is not in pending status")
        
        # Create Stripe payment intent
        payment_data = await StripeService.create_payment_intent(amount, order_id)
        
        # Update order with payment intent ID
        order.payment_intent_id = payment_data['payment_intent_id']
        order.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(order)
        
        return payment_data
    

