from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from typing import List
from database import get_session
from models import (
    UserOrder, UserOrderRead, UserTicketRead
)
from Order.services.order_service import OrderService

router = APIRouter()

@router.post("/create-from-cart/{user_id}", response_model=UserOrderRead, status_code=status.HTTP_201_CREATED)
def create_order_from_cart(
    user_id: int,
    payment_method: str,
    session: Session = Depends(get_session)
):
    """Create order from user's cart items"""
    return OrderService.create_order_from_cart(session, user_id, payment_method)

@router.post("/{order_id}/complete", response_model=UserOrderRead)
def complete_order(order_id: int, session: Session = Depends(get_session)):
    """Complete order by creating user tickets and clearing cart"""
    return OrderService.complete_order(session, order_id)

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

@router.get("/user/{user_id}", response_model=List[UserOrderRead])
def get_user_orders(user_id: int, session: Session = Depends(get_session)):
    """Get all orders for a user"""
    return OrderService.get_user_orders(session, user_id)

@router.get("/{order_id}/tickets", response_model=List[UserTicketRead])
def get_order_tickets(order_id: int, session: Session = Depends(get_session)):
    """Get all tickets for an order"""
    return OrderService.get_order_tickets(session, order_id)

@router.get("/{order_id}/details")
def get_order_with_details(order_id: int, session: Session = Depends(get_session)):
    """Get order with complete details including tickets"""
    return OrderService.get_order_with_details(session, order_id)
