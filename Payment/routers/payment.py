from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from database import get_session
from models import (
    CreatePaymentIntentRequest, 
    CreatePaymentIntentResponse,
    CompleteOrderRequest,
    UpdateOrderStatusRequest,
    UserOrderRead,
    OrderStatus
)
from Payment.services.payment_order_service import PaymentOrderService

router = APIRouter()

@router.post("/create-payment-intent", response_model=CreatePaymentIntentResponse)
async def create_payment_intent(
    request: CreatePaymentIntentRequest,
    session: Session = Depends(get_session)
):
    """Create a Stripe payment intent for an order"""
    try:
        payment_data = await PaymentOrderService.create_payment_intent(
            session, request.orderId, request.amount
        )
        return CreatePaymentIntentResponse(
            client_secret=payment_data['client_secret'],
            payment_intent_id=payment_data['payment_intent_id']
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{order_id}/complete", response_model=UserOrderRead)
async def complete_order(
    order_id: int,
    request: CompleteOrderRequest,
    session: Session = Depends(get_session)
):
    """Complete an order after successful payment"""
    try:
        order = await PaymentOrderService.complete_order(
            session, order_id, request.paymentIntentId
        )
        return UserOrderRead.model_validate(order)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/{order_id}/status", response_model=UserOrderRead)
async def update_order_status(
    order_id: int,
    request: UpdateOrderStatusRequest,
    session: Session = Depends(get_session)
):
    """Update order status"""
    try:
        order = PaymentOrderService.update_order_status(session, order_id, request.status)
        return UserOrderRead.model_validate(order)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{order_id}", response_model=UserOrderRead)
async def get_order(
    order_id: int,
    session: Session = Depends(get_session)
):
    """Get order details"""
    order = PaymentOrderService.get_order(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return UserOrderRead.model_validate(order)
