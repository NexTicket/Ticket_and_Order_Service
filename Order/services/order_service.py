from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from models import (
    UserOrder, UserOrderCreate, UserOrderRead, UserOrderUpdate,
    CartItem, UserTicket, Transaction, TransactionCreate,
    User, BulkTicket, OrderStatus, TransactionStatus
)
from Ticket.services.ticket_service import TicketService
from Order.services.cart_service import CartService

class OrderService:
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
    def complete_order(session: Session, order_id: int) -> UserOrder:
        """Complete order by creating user tickets and clearing cart"""
        order = session.get(UserOrder, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.status != OrderStatus.PENDING:
            raise HTTPException(status_code=400, detail="Order is not in pending status")
        
        # Get user's cart items
        cart_items = CartService.get_user_cart(session, order.user_id)
        if not cart_items:
            raise HTTPException(status_code=400, detail="No cart items found for this order")
        
        # Create user tickets from cart
        user_tickets = TicketService.create_user_tickets_from_order(session, order, cart_items)
        
        # Update order status
        order.status = OrderStatus.COMPLETED
        session.add(order)
        
        # Update transaction status
        transaction = session.exec(
            select(Transaction).where(Transaction.order_id == order_id)
        ).first()
        if transaction:
            transaction.status = TransactionStatus.SUCCESS
            session.add(transaction)
        
        # Clear user's cart
        CartService.clear_user_cart(session, order.user_id)
        
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
