from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
from models import (
    UserOrder, UserOrderCreate, UserOrderRead, UserOrderUpdate,
    UserTicket, Transaction, TransactionCreate,
    BulkTicket, OrderStatus, TransactionStatus,
    RedisOrderItem, OrderSummaryResponse,
    SeatOrder, SeatOrderCreate
)
from Ticket.services.ticket_service import TicketService
from Order.services.ticket_locking_service import TicketLockingService
from Payment.services.stripe_service import StripeService
from Database.redis_client import redis_conn

class OrderService:
    
    @staticmethod
    def get_redis_order_summary(firebase_uid: str) -> Optional[OrderSummaryResponse]:
        """Get order summary from Redis"""
        order_data = TicketLockingService._get_user_order_data(firebase_uid)
        
        if not order_data:
            return None
        
        # Parse order data
        seat_ids = json.loads(order_data.get('seat_ids', '[]'))
        event_id = int(order_data.get('event_id'))
        expires_at = datetime.fromisoformat(order_data['expires_at'])
        remaining_seconds = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
        
        if remaining_seconds <= 0:
            return None
        
        # Get bulk ticket info if available
        bulk_ticket_info = {}
        if order_data.get('bulk_ticket_info'):
            try:
                bulk_ticket_info = json.loads(order_data['bulk_ticket_info'])
            except json.JSONDecodeError:
                bulk_ticket_info = {}
        
        # Calculate pricing
        price_per_seat = bulk_ticket_info.get('price_per_seat', 0.0)
        total_amount = price_per_seat * len(seat_ids)
        
        items = [RedisOrderItem(
            bulk_ticket_id=bulk_ticket_info.get('bulk_ticket_id', 0),
            seat_ids=seat_ids,
            quantity=len(seat_ids),
            price_per_seat=price_per_seat
        )]
        
        return OrderSummaryResponse(
            order_id=order_data['order_id'],
            user_id=firebase_uid,
            total_seats=len(seat_ids),
            total_amount=total_amount,
            items=items,
            expires_at=expires_at,
            remaining_seconds=remaining_seconds
        )
    
    @staticmethod
    def add_payment_to_order(session: Session, firebase_uid: str, payment_method: str) -> UserOrder:
        """Create or update transaction for an existing order from Redis"""
        # Get order data from Redis
        order_data = TicketLockingService._get_user_order_data(firebase_uid)
        if not order_data:
            raise HTTPException(status_code=400, detail="No temporary order found or order expired")
        
        # Parse order data
        seat_ids = json.loads(order_data.get('seat_ids', '[]'))
        event_id = int(order_data.get('event_id'))
        order_id = order_data.get('order_id')
        
        if not seat_ids:
            raise HTTPException(status_code=400, detail="No seats in order")
        
        if not order_id:
            raise HTTPException(status_code=400, detail="Invalid order data: missing order_id")
        
        # Get existing order from database
        db_order = session.get(UserOrder, order_id)
        if not db_order:
            raise HTTPException(status_code=404, detail="Order not found in database")
        
        if db_order.status != OrderStatus.PENDING:
            raise HTTPException(status_code=400, detail=f"Order is in {db_order.status} status, expected PENDING")
        
        # Verify user owns this order
        if db_order.firebase_uid != firebase_uid:
            raise HTTPException(status_code=403, detail="Order belongs to another user")
        
        # Create transaction for the order
        transaction_data = TransactionCreate(
            order_id=db_order.id,
            amount=db_order.total_amount,
            payment_method=payment_method,
            status=TransactionStatus.PENDING
        )
        
        db_transaction = Transaction.model_validate(transaction_data)
        session.add(db_transaction)
        session.commit()
        
        # Update order updated_at timestamp
        db_order.updated_at = datetime.now(timezone.utc)
        session.add(db_order)
        session.commit()
        session.refresh(db_order)
        
        return db_order
    
    @staticmethod
    async def complete_order(session: Session, order_id: str, payment_intent_id: str, firebase_uid: str) -> UserOrder:
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
        
        # Get seat assignments from the OrderSeatAssignment table first
        seat_assignments = OrderService.get_order_seat_assignments(session, order_id)
        
        if not seat_assignments:
            # Fall back to getting seat assignments from order notes if not found in table
            if not order.notes:
                raise HTTPException(status_code=400, detail="No seat assignment data found in order")
            
            try:
                order_data = json.loads(order.notes)
                seat_assignments_dict = order_data.get("seat_assignments", {})
                if not seat_assignments_dict:
                    raise HTTPException(status_code=400, detail="No seat assignments found in order notes")
                
                # Process seat assignments from order notes
                user_tickets = []
                for bulk_ticket_id, seat_ids in seat_assignments_dict.items():
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
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid order data format")
        else:
            # Process seat assignments from OrderSeatAssignment table
            user_tickets = []
            for seat_assignment in seat_assignments:
                bulk_ticket = session.get(BulkTicket, seat_assignment.bulk_ticket_id)
                if not bulk_ticket:
                    continue
                
                seat_ids = json.loads(seat_assignment.seat_ids)
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
        
        # Clear Redis order (no need to cancel order since we're completing it)
        TicketLockingService._cleanup_user_locks(firebase_uid)
        
        session.commit()
        session.refresh(order)
        
        return order
    
    @staticmethod
    def cancel_order(session: Session, order_id: str) -> UserOrder:
        """Cancel an order"""
        order = session.get(UserOrder, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.status not in [OrderStatus.PENDING]:
            raise HTTPException(status_code=400, detail="Cannot cancel this order")
        
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.now(timezone.utc)
        session.add(order)
        
        # Update transaction status
        transaction = session.exec(
            select(Transaction).where(Transaction.order_id == order_id)
        ).first()
        if transaction:
            transaction.status = TransactionStatus.FAILED
            transaction.updated_at = datetime.now(timezone.utc)
            session.add(transaction)
        
        # We don't need to modify seat assignments when cancelling the order
        # They remain as a record of what seats were initially assigned
        
        session.commit()
        session.refresh(order)
        
        return order
    
    @staticmethod
    def get_order(session: Session, order_id: str) -> Optional[UserOrder]:
        """Get order by ID"""
        return session.get(UserOrder, order_id)
    
    @staticmethod
    def get_user_orders(session: Session, firebase_uid: str) -> List[UserOrder]:
        """Get all orders for a user by Firebase UID"""
        statement = select(UserOrder).where(UserOrder.firebase_uid == firebase_uid)
        return session.exec(statement).all()
    
    @staticmethod
    def get_order_tickets(session: Session, order_id: str) -> List[UserTicket]:
        """Get all tickets for an order"""
        statement = select(UserTicket).where(UserTicket.order_id == order_id)
        return session.exec(statement).all()
    
    @staticmethod
    def get_order_with_details(session: Session, order_id: str) -> dict:
        """Get order with complete details including tickets"""
        order = session.get(UserOrder, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        tickets = OrderService.get_order_tickets(session, order_id)
        
        transactions = session.exec(
            select(Transaction).where(Transaction.order_id == order_id)
        ).all()
        
        seat_assignments = session.exec(
            select(SeatOrder).where(SeatOrder.order_id == order_id)
        ).all()
        
        return {
            "order": order,
            "tickets": tickets,
            "transactions": transactions,
            "seat_assignments": seat_assignments
        }
    
    @staticmethod
    def get_order_seat_assignments(session: Session, order_id: str) -> List[SeatOrder]:
        """Get seat assignments for an order"""
        statement = select(SeatOrder).where(SeatOrder.order_id == order_id)
        return session.exec(statement).all()
    
