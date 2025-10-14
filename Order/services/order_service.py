from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
import logging
from models import (
    UserOrder,
    UserTicket, Transactions,
    BulkTicket, OrderStatus, TransactionStatus,
    RedisOrderItem, OrderSummaryResponse,
    SeatOrder
)
from Ticket.services.ticket_service import TicketService
from Order.services.ticket_locking_service import TicketLockingService
from Order.services.transaction_service import TransactionService
from Payment.services.stripe_service import StripeService
from Database.redis_client import redis_conn
from kafka.kafka_producer import send_message

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
        
        # Create transaction for the order using transaction service
        transaction = TransactionService.create_transaction(
            session=session,
            order_id=db_order.id,
            amount=db_order.total_amount,
            payment_method=payment_method,
            transaction_reference="Payment initiated",
            status=TransactionStatus.PENDING
        )
        
        if not transaction:
            raise HTTPException(status_code=500, detail="Failed to create transaction record")
        
        # Update order updated_at timestamp
        db_order.updated_at = datetime.now(timezone.utc)
        session.add(db_order)
        session.commit()
        session.refresh(db_order)
        
        return db_order
    
    @staticmethod
    async def complete_order(session: Session, order_id: str, payment_intent_id: str) -> UserOrder:
        """
        Securely completes an order after successful payment, creating one ticket per seat
        in a single atomic transaction.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Starting atomic order completion for order_id: {order_id}")
        
        # 1. Fetch the Order and perform initial validation.
        order = session.get(UserOrder, order_id)
        if not order:
            logger.error(f"Order {order_id} not found")
            raise HTTPException(status_code=404, detail="Order not found")
        
        logger.info(f"Found order {order_id} with status {order.status}")
        
        if order.status != OrderStatus.PENDING:
            # Idempotency check: If it's already completed with the same payment, it's a success.
            if order.status == OrderStatus.COMPLETED and order.stripe_payment_id == payment_intent_id:
                logger.warning(f"Webhook re-delivery: Order {order_id} already completed.")
                return order
            logger.error(f"Order {order_id} is in {order.status} status, not PENDING")
            raise HTTPException(status_code=400, detail=f"Order is not in pending status (current: {order.status})")
        
        # Verify payment intent ID matches
        stored_payment_intent_id = order.payment_intent_id
        logger.info(f"Comparing payment intent IDs: stored={stored_payment_intent_id}, received={payment_intent_id}")
        
        # For webhook handling, we'll be lenient if the payment intent ID isn't set in the order yet
        if stored_payment_intent_id and stored_payment_intent_id != payment_intent_id:
            logger.error(f"Payment intent ID mismatch: {stored_payment_intent_id} != {payment_intent_id}")
            raise HTTPException(status_code=400, detail=f"Payment intent ID mismatch")
        
        # Verify payment with Stripe
        logger.info(f"Verifying payment success with Stripe")
        is_payment_successful = await StripeService.verify_payment_success(payment_intent_id)
        if not is_payment_successful:
            logger.error(f"Payment verification failed for intent {payment_intent_id}")
            raise HTTPException(status_code=400, detail="Payment not successful")
        
        # 2. Fetch all seat assignments for this order
        seat_assignments = session.exec(
            select(SeatOrder).where(SeatOrder.order_id == order_id)
        ).all()
        
        if not seat_assignments:
            logger.error(f"FATAL: No SeatOrder records found for pending order {order_id}.")
            
            # Fall back to getting seat assignments from order notes if not found in table
            if not order.notes:
                raise HTTPException(status_code=400, detail="Cannot complete order: seat assignment data is missing.")
            
            try:
                # Note: This fallback is deprecated and will eventually be removed
                logger.warning(f"Falling back to order notes for seat assignments in order {order_id}")
                order_data = json.loads(order.notes)
                seat_assignments_dict = order_data.get("seat_assignments", {})
                if not seat_assignments_dict:
                    raise HTTPException(status_code=400, detail="No seat assignments found in order notes")
                
                # We would process from notes here, but this approach is deprecated
                # and better to fail properly than use potentially inconsistent data
                raise HTTPException(status_code=400, detail="Using seat assignments from order notes is no longer supported")
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid order data format")
        
        # 3. Efficiently pre-fetch all needed BulkTicket records to avoid queries in a loop
        bulk_ticket_ids = {sa.bulk_ticket_id for sa in seat_assignments}
        bulk_tickets_query = session.exec(
            select(BulkTicket).where(BulkTicket.id.in_(bulk_ticket_ids))
        ).all()
        bulk_tickets_map = {bt.id: bt for bt in bulk_tickets_query}
        
        try:
            # Create a list to collect QR codes for notification
            qr_codes = []
            
            # 4. Loop through each assignment and each seat to create individual UserTickets
            for seat_assignment in seat_assignments:
                bulk_ticket = bulk_tickets_map.get(seat_assignment.bulk_ticket_id)
                if not bulk_ticket:
                    logger.error(f"BulkTicket ID {seat_assignment.bulk_ticket_id} not found for order {order_id}.")
                    raise ValueError(f"Configuration error: BulkTicket not found.")  # Internal error
                
                try:
                    seat_ids = json.loads(seat_assignment.seat_ids)
                except json.JSONDecodeError:
                    logger.error(f"Invalid seat_ids JSON for SeatOrder {seat_assignment.id}.")
                    raise ValueError("Invalid seat data.")
                
                # Check if there are enough available seats before processing
                if bulk_ticket.available_seats < len(seat_ids):
                    logger.error(f"Overselling detected for BulkTicket {bulk_ticket.id}! "
                                f"Required: {len(seat_ids)}, Available: {bulk_ticket.available_seats}")
                    raise HTTPException(status_code=409, detail="Not enough available seats to complete the order.")
                
                # Process each seat individually
                for seat_id in seat_ids:
                    # Create one UserTicket per seat
                    user_ticket = UserTicket(
                        order_id=order.id,
                        bulk_ticket_id=bulk_ticket.id,
                        firebase_uid=order.firebase_uid,
                        seat_id=seat_id,
                        price_paid=bulk_ticket.price,
                        status="sold"
                    )
                    
                    # Generate unique QR code data for this specific ticket
                    qr_data = {
                        "ticket_id": f"ticket_{order.id}_{seat_id}",
                        "event_id": bulk_ticket.event_id,
                        "venue_id": bulk_ticket.venue_id,
                        "seat_id": seat_id,
                        "firebase_uid": order.firebase_uid,
                        "order_ref": order.order_reference
                    }
                    qr_data_str = json.dumps(qr_data)
                    user_ticket.qr_code_data = qr_data_str
                    
                    # Add QR code to the list for notification
                    qr_codes.append(qr_data_str)
                    
                    session.add(user_ticket)
                    
                    # Decrement available seat count for each ticket created
                    bulk_ticket.available_seats -= 1
            
            # 5. Finalize the order and transaction details
            order.status = OrderStatus.COMPLETED
            order.stripe_payment_id = payment_intent_id
            order.completed_at = datetime.now(timezone.utc)
            order.updated_at = datetime.now(timezone.utc)
            session.add(order)
            
            # Update transaction status or create a new transaction if none exists
            transaction = session.exec(
                select(Transactions).where(Transactions.order_id == order_id)
            ).first()
            
            if transaction:
                # Update existing transaction using transaction service
                TransactionService.update_transaction_status(
                    session=session,
                    transaction_id=transaction.transaction_id,
                    status=TransactionStatus.SUCCESS,
                    transaction_reference=f"Payment completed: {payment_intent_id}"
                )
                logger.info(f"Updated existing transaction for order {order_id}")
            else:
                # Create a new transaction if none exists using transaction service
                logger.info(f"No transaction found for order {order_id}, creating one")
                TransactionService.create_transaction(
                    session=session,
                    order_id=order_id,
                    amount=order.total_amount,
                    payment_method="stripe",
                    status=TransactionStatus.SUCCESS,
                    transaction_reference=f"Payment completed: {payment_intent_id}"
                )
                logger.info(f"Created new transaction for order {order_id}")
            
            # 6. Commit all changes to the database at once
            session.commit()
            logger.info(f"Successfully completed order {order_id} and committed to database.")
            
        except Exception as e:
            logger.error(f"An error occurred during transaction for order {order_id}. Rolling back. Error: {e}")
            session.rollback()  # Rollback all changes if any step failed
            raise HTTPException(status_code=500, detail=f"Failed to complete order due to an internal error: {str(e)}")
        
        # 7. Send completed order notification with all QR codes to Kafka in a separate try-catch block
        # This way, notification failures won't affect the order transaction which is already committed
        if order.status == OrderStatus.COMPLETED:
            try:
                logger.info(f"Sending order completion notification for order {order_id}")
                
                # Use the qr_codes we already collected during ticket creation
                # Send consolidated notification with all data
                notification_data = {
                    "order_id": order.id,
                    "firebase_uid": order.firebase_uid,
                    "total_amount": float(order.total_amount),
                    "qr_codes": qr_codes,
                    "notification_type": "order_completed"
                }
                
                # Use the generic send_message function to send all data in one message
                send_message(
                    topic="ticket_notifications", 
                    key=order.firebase_uid, 
                    data=notification_data,
                    headers={
                        "service": b"ticket-order-service",
                        "message_type": b"order_completed"
                    }
                )
                
                logger.info(f"Successfully sent notification for order {order_id} with {len(qr_codes)} tickets")
            except Exception as kafka_error:
                # The order succeeded, but notification failed.
                # DO NOT raise an HTTPException here. The user's order is fine.
                # This is an internal problem that we must log for monitoring or retry.
                logger.error(f"ALERT: Order {order_id} committed, but Kafka notification failed. Error: {kafka_error}")
                # The system needs a way to handle these missed notifications,
                # but the user's request was successful.
            
        # Refresh the object to reflect committed changes
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
        
        # Update transaction status or create a new one for the cancellation
        transaction = session.exec(
            select(Transactions).where(Transactions.order_id == order_id)
        ).first()
        
        if transaction:
            # Update existing transaction using transaction service
            TransactionService.update_transaction_status(
                session=session,
                transaction_id=transaction.transaction_id,
                status=TransactionStatus.FAILED,
                transaction_reference="Order cancelled"
            )
        else:
            # Create a new transaction for the cancellation using transaction service
            TransactionService.create_transaction(
                session=session,
                order_id=order_id,
                amount=order.total_amount,
                payment_method="system",
                status=TransactionStatus.FAILED,
                transaction_reference="Order cancelled"
            )
        
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
            select(Transactions).where(Transactions.order_id == order_id)
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
    
