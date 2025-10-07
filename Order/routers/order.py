from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from typing import List, Optional
from database import get_session
from firebase_auth import get_current_user_from_token
from models import (
    UserOrder, UserOrderRead, UserTicketRead,
    CreatePaymentIntentRequest, CreatePaymentIntentResponse,
    CompleteOrderRequest, AddPaymentToOrderRequest, OrderSummaryResponse
)
from Order.services.order_service import OrderService

router = APIRouter()

@router.get("/order-summary", response_model=Optional[OrderSummaryResponse])
def get_order_summary(
    current_user: dict = Depends(get_current_user_from_token)
):
    """Get summary of current Redis order"""
    firebase_uid = current_user['uid']
    return OrderService.get_redis_order_summary(firebase_uid)

@router.post("/add-payment", response_model=UserOrderRead, status_code=status.HTTP_201_CREATED)
def add_payment_to_order(
    request: AddPaymentToOrderRequest,
    current_user: dict = Depends(get_current_user_from_token),
    session: Session = Depends(get_session)
):
    """Add payment to existing order"""
    firebase_uid = current_user['uid']
    return OrderService.add_payment_to_order(
        session, firebase_uid, request.payment_method
    )

@router.post("/{order_id}/complete", response_model=UserOrderRead)
async def complete_order(
    order_id: int,
    request: CompleteOrderRequest,
    current_user: dict = Depends(get_current_user_from_token),
    session: Session = Depends(get_session)
):
    """Complete order with payment verification, create user tickets and clean up Redis data"""
    try:
        firebase_uid = current_user['uid']
        order = await OrderService.complete_order(
            session, order_id, request.paymentIntentId, firebase_uid
        )
        return UserOrderRead.model_validate(order)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{order_id}/cancel", response_model=UserOrderRead)
def cancel_order(order_id: int, session: Session = Depends(get_session)):
    """Cancel an order"""
    return OrderService.cancel_order(session, order_id)

@router.get("/{order_id}", response_model=UserOrderRead)
def get_order(order_id: int, session: Session = Depends(get_session)):
    """Get order by ID"""
    order = OrderService.get_order(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.get("/my-orders", response_model=List[UserOrderRead])
def get_my_orders(
    current_user: dict = Depends(get_current_user_from_token),
    session: Session = Depends(get_session)
):
    """Get all orders for the authenticated user"""
    firebase_uid = current_user['uid']
    return OrderService.get_user_orders(session, firebase_uid)

@router.get("/user/{firebase_uid}", response_model=List[UserOrderRead])
def get_user_orders_by_uid(firebase_uid: str, session: Session = Depends(get_session)):
    """Get all orders for a user by Firebase UID (admin function)"""
    return OrderService.get_user_orders(session, firebase_uid)

@router.get("/{order_id}/tickets", response_model=List[UserTicketRead])
def get_order_tickets(order_id: int, session: Session = Depends(get_session)):
    """Get all tickets for an order"""
    return OrderService.get_order_tickets(session, order_id)

@router.get("/{order_id}/details")
def get_order_with_details(order_id: int, session: Session = Depends(get_session)):
    """Get order with complete details including tickets"""
    return OrderService.get_order_with_details(session, order_id)

@router.post("/create-payment-intent", response_model=CreatePaymentIntentResponse)
async def create_payment_intent(
    request: CreatePaymentIntentRequest,
    session: Session = Depends(get_session)
):
    """Create a Stripe payment intent for an order"""
    try:
        payment_data = await OrderService.create_payment_intent(
            session, request.orderId, request.amount
        )
        return CreatePaymentIntentResponse(
            client_secret=payment_data['client_secret'],
            payment_intent_id=payment_data['payment_intent_id']
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


