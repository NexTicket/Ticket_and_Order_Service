from sqlmodel import Session
from typing import Optional
from fastapi import HTTPException
from datetime import datetime, timezone
from models import UserOrder, OrderStatus
from Payment.services.stripe_service import StripeService

class PaymentOrderService:
    @staticmethod
    def get_order(session: Session, order_id: int) -> Optional[UserOrder]:
        """Get order by ID"""
        return session.get(UserOrder, order_id)
    
    @staticmethod
    def update_order_status(session: Session, order_id: int, status: OrderStatus) -> UserOrder:
        """Update order status"""
        order = PaymentOrderService.get_order(session, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        order.status = status
        order.updated_at = datetime.now(timezone.utc)
        
        if status == OrderStatus.COMPLETED:
            order.completed_at = datetime.now(timezone.utc)
        
        session.commit()
        session.refresh(order)
        return order
    
    @staticmethod
    async def create_payment_intent(session: Session, order_id: int, amount: int):
        """Create payment intent and update order"""
        order = PaymentOrderService.get_order(session, order_id)
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
    
    @staticmethod
    async def complete_order(session: Session, order_id: int, payment_intent_id: str) -> UserOrder:
        """Complete order after successful payment"""
        order = PaymentOrderService.get_order(session, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.payment_intent_id != payment_intent_id:
            raise HTTPException(status_code=400, detail="Payment intent ID mismatch")
        
        # Verify payment with Stripe
        is_payment_successful = await StripeService.verify_payment_success(payment_intent_id)
        if not is_payment_successful:
            raise HTTPException(status_code=400, detail="Payment not successful")
        
        # Update order status
        order.status = OrderStatus.COMPLETED
        order.stripe_payment_id = payment_intent_id
        order.completed_at = datetime.now(timezone.utc)
        order.updated_at = datetime.now(timezone.utc)
        
        session.commit()
        session.refresh(order)
        
        return order
