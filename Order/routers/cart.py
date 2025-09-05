from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from typing import List
from database import get_session
from models import (
    CartItem, CartItemCreate, CartItemRead, CartItemUpdate,
    CartSummary
)
from Order.services.cart_service import CartService

router = APIRouter()

@router.post("/", response_model=CartItemRead, status_code=status.HTTP_201_CREATED)
def add_to_cart(cart_item: CartItemCreate, session: Session = Depends(get_session)):
    """Add item to cart with preferred seat selection"""
    return CartService.add_to_cart(session, cart_item)

@router.get("/user/{user_id}", response_model=List[CartItemRead])
def get_user_cart(user_id: int, session: Session = Depends(get_session)):
    """Get all cart items for a user"""
    return CartService.get_user_cart(session, user_id)

@router.get("/user/{user_id}/summary", response_model=CartSummary)
def get_cart_summary(user_id: int, session: Session = Depends(get_session)):
    """Get cart summary with total items and amount"""
    return CartService.get_cart_summary(session, user_id)

@router.put("/{cart_item_id}")
def update_cart_item(
    cart_item_id: int,
    update_data: CartItemUpdate,
    session: Session = Depends(get_session)
):
    """Update cart item quantity and preferred seats"""
    updated_item = CartService.update_cart_item(session, cart_item_id, update_data)
    if not updated_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    return updated_item

@router.delete("/{cart_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_cart(cart_item_id: int, session: Session = Depends(get_session)):
    """Remove item from cart"""
    success = CartService.remove_from_cart(session, cart_item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Cart item not found")

@router.delete("/user/{user_id}/clear", status_code=status.HTTP_204_NO_CONTENT)
def clear_user_cart(user_id: int, session: Session = Depends(get_session)):
    """Clear all items from user's cart"""
    CartService.clear_user_cart(session, user_id)
