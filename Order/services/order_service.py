from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from models import (
    UserOrder, UserOrderCreate, UserOrderRead, UserOrderUpdate,
    CartItem, UserTicket, Transaction, TransactionCreate,
    BulkTicket, OrderStatus, TransactionStatus, SeatReservation, ReservationStatus
)
from Ticket.services.ticket_service import TicketService
from Order.services.cart_service import CartService
from Payment.services.stripe_service import StripeService
from services.seat_management_service import SeatManagementService
import httpx
import os
import json

class OrderService:
    EVENT_VENUE_SERVICE_URL = os.getenv("EVENT_VENUE_SERVICE_URL", "http://localhost:4000")
    
    @staticmethod
    async def _fetch_order_details(bulk_tickets: List[BulkTicket]) -> Dict[str, Any]:
        """Fetch event and venue details for order"""
        order_details = {
            "events": {},
            "venues": {},
            "items": []
        }
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Get unique event and venue IDs
                event_ids = set()
                venue_ids = set()
                for bt in bulk_tickets:
                    if bt.external_event_id:
                        event_ids.add(bt.external_event_id)
                    if bt.external_venue_id:
                        venue_ids.add(bt.external_venue_id)
                
                # Fetch events
                for event_id in event_ids:
                    try:
                        response = await client.get(f"{OrderService.EVENT_VENUE_SERVICE_URL}/api/events/{event_id}")
                        if response.status_code == 200:
                            order_details["events"][str(event_id)] = response.json()
                    except Exception as e:
                        print(f"Failed to fetch event {event_id}: {e}")
                
                # Fetch venues
                for venue_id in venue_ids:
                    try:
                        response = await client.get(f"{OrderService.EVENT_VENUE_SERVICE_URL}/api/venues/{venue_id}")
                        if response.status_code == 200:
                            order_details["venues"][str(venue_id)] = response.json()
                    except Exception as e:
                        print(f"Failed to fetch venue {venue_id}: {e}")
                        
        except Exception as e:
            print(f"Error fetching order details: {e}")
        
        return order_details
    
    @staticmethod
    def create_order_from_cart(session: Session, user_id: int, payment_method: str) -> UserOrder:
        """Create order from user's cart items"""
        # Get user cart
        cart_items = CartService.get_user_cart(session, user_id)
        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")
        
        # Calculate total amount and verify availability
        total_amount = 0
        for cart_item in cart_items:
            bulk_ticket = session.get(BulkTicket, cart_item.bulk_ticket_id)
            if not bulk_ticket:
                raise HTTPException(status_code=404, detail=f"Bulk ticket {cart_item.bulk_ticket_id} not found")
            
            if bulk_ticket.available_seats < cart_item.quantity:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Not enough seats available for {bulk_ticket.seat_type} tickets"
                )
            
            total_amount += bulk_ticket.price * cart_item.quantity
        
        # Create order
        order_data = UserOrderCreate(
            user_id=user_id,
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
        
        return db_order
    
    @staticmethod
    async def create_order_from_cart_by_firebase_uid(session: Session, firebase_uid: str, payment_method: str) -> UserOrder:
        """Create order from user's cart items using Firebase UID"""
        # Get user cart by Firebase UID
        cart_items = CartService.get_user_cart_by_firebase_uid(session, firebase_uid)
        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")
        
        # Calculate total amount and verify availability
        total_amount = 0
        bulk_tickets = []
        
        for cart_item in cart_items:
            bulk_ticket = session.get(BulkTicket, cart_item.bulk_ticket_id)
            if not bulk_ticket:
                raise HTTPException(status_code=404, detail=f"Bulk ticket {cart_item.bulk_ticket_id} not found")
            
            if bulk_ticket.available_seats < cart_item.quantity:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Not enough seats available for {bulk_ticket.seat_type} tickets"
                )
            
            total_amount += bulk_ticket.price * cart_item.quantity
            bulk_tickets.append(bulk_ticket)
        
        # Fetch event and venue details for the order
        order_details = await OrderService._fetch_order_details(bulk_tickets)
        
        # Create detailed notes with cart information
        order_notes = {
            "cart_items_count": len(cart_items),
            "total_tickets": sum(item.quantity for item in cart_items),
            "payment_method": payment_method,
            "events": order_details["events"],
            "venues": order_details["venues"],
            "items": []
        }
        
        # Add cart item details to notes
        for cart_item in cart_items:
            bulk_ticket = session.get(BulkTicket, cart_item.bulk_ticket_id)
            if bulk_ticket:
                item_details = {
                    "bulk_ticket_id": bulk_ticket.id,
                    "seat_type": bulk_ticket.seat_type.value,
                    "price": bulk_ticket.price,
                    "quantity": cart_item.quantity,
                    "preferred_seat_ids": cart_item.preferred_seat_ids,
                    "event_id": bulk_ticket.external_event_id,
                    "venue_id": bulk_ticket.external_venue_id
                }
                order_notes["items"].append(item_details)
        
        # Create order
        order_data = UserOrderCreate(
            firebase_uid=firebase_uid,
            total_amount=total_amount,
            status=OrderStatus.PENDING,
            notes=json.dumps(order_notes)  # Store detailed information as JSON
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
        
        return db_order
    
    @staticmethod
    async def complete_order(session: Session, order_id: int, payment_intent_id: str) -> UserOrder:
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
        
        # Get user's cart items by Firebase UID
        cart_items = CartService.get_user_cart_by_firebase_uid(session, order.firebase_uid)
        if not cart_items:
            raise HTTPException(status_code=400, detail="No cart items found for this order")
        
        # Create user tickets from cart
        user_tickets = TicketService.create_user_tickets_from_order(session, order, cart_items)
        
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
            session.add(transaction)
        
        # Clear user's cart by Firebase UID
        CartService.clear_user_cart_by_firebase_uid(session, order.firebase_uid)
        
        # Update seat reservations to CONFIRMED status and update bulk ticket availability
        # Parse order notes to get the bulk ticket and seat information
        if order.notes:
            try:
                order_details = json.loads(order.notes)
                for item in order_details.get("items", []):
                    bulk_ticket = session.get(BulkTicket, item["bulk_ticket_id"])
                    if bulk_ticket:
                        # Reduce available seats as they are now sold
                        bulk_ticket.available_seats = max(0, bulk_ticket.available_seats - item["quantity"])
                        session.add(bulk_ticket)
                    
                    # Update seat reservations to CONFIRMED status using consolidated service
                    if item.get("preferred_seat_ids"):
                        try:
                            # Use consolidated service to confirm seat reservations
                            SeatManagementService.confirm_reservations_for_order(
                                session=session,
                                firebase_uid=order.firebase_uid,
                                order_id=order.id
                            )
                        except json.JSONDecodeError:
                            print(f"Failed to parse seat IDs for order {order_id}")
            except json.JSONDecodeError:
                print(f"Failed to parse order notes for order {order_id}")
        
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
    def get_user_orders(session: Session, user_id: int) -> List[UserOrder]:
        """Get all orders for a user"""
        statement = select(UserOrder).where(UserOrder.user_id == user_id)
        return session.exec(statement).all()
    
    @staticmethod
    def get_user_orders_by_firebase_uid(session: Session, firebase_uid: str) -> List[UserOrder]:
        """Get all orders for a user by Firebase UID"""
        statement = select(UserOrder).where(UserOrder.firebase_uid == firebase_uid)
        return session.exec(statement).all()
    
    @staticmethod
    def get_user_tickets_by_firebase_uid(session: Session, firebase_uid: str) -> List[UserTicket]:
        """Get all tickets for a user by Firebase UID"""
        statement = select(UserTicket).where(UserTicket.firebase_uid == firebase_uid)
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
    

