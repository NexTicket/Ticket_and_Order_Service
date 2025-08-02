from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from models import (
    CartItem, CartItemCreate, CartItemRead,
    User, BulkTicket, CartSummary
)
import json

class CartService:
    @staticmethod
    def add_to_cart(session: Session, cart_data: CartItemCreate) -> CartItem:
        """Add item to cart with preferred seat selection"""
        # Verify user exists
        user = session.get(User, cart_data.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify bulk ticket exists
        bulk_ticket = session.get(BulkTicket, cart_data.bulk_ticket_id)
        if not bulk_ticket:
            raise HTTPException(status_code=404, detail="Bulk ticket not found")
        
        # Check if there are enough available seats
        if bulk_ticket.available_seats < cart_data.quantity:
            raise HTTPException(
                status_code=400, 
                detail=f"Only {bulk_ticket.available_seats} seats available"
            )
        
        # Validate preferred seat IDs format
        try:
            preferred_seats = json.loads(cart_data.preferred_seat_ids)
            if not isinstance(preferred_seats, list):
                raise ValueError("Preferred seats must be a list")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid preferred seat IDs format")
        
        # Check if item already exists in cart for this user and bulk ticket
        existing_cart_item = session.exec(
            select(CartItem).where(
                CartItem.user_id == cart_data.user_id,
                CartItem.bulk_ticket_id == cart_data.bulk_ticket_id
            )
        ).first()
        
        if existing_cart_item:
            # Update existing item
            existing_cart_item.quantity = cart_data.quantity
            existing_cart_item.preferred_seat_ids = cart_data.preferred_seat_ids
            session.add(existing_cart_item)
            session.commit()
            session.refresh(existing_cart_item)
            return existing_cart_item
        else:
            # Create new cart item
            db_cart_item = CartItem.model_validate(cart_data)
            session.add(db_cart_item)
            session.commit()
            session.refresh(db_cart_item)
            return db_cart_item
    
    @staticmethod
    def get_user_cart(session: Session, user_id: int) -> List[CartItem]:
        """Get all cart items for a user"""
        statement = select(CartItem).where(CartItem.user_id == user_id)
        return session.exec(statement).all()
    
    @staticmethod
    def get_cart_summary(session: Session, user_id: int) -> CartSummary:
        """Get cart summary with total items and amount"""
        cart_items = CartService.get_user_cart(session, user_id)
        
        total_items = sum(item.quantity for item in cart_items)
        total_amount = 0
        
        cart_reads = []
        for item in cart_items:
            bulk_ticket = session.get(BulkTicket, item.bulk_ticket_id)
            if bulk_ticket:
                total_amount += bulk_ticket.price * item.quantity
            
            cart_reads.append(CartItemRead.model_validate(item))
        
        return CartSummary(
            total_items=total_items,
            total_amount=total_amount,
            items=cart_reads
        )
    
    @staticmethod
    def update_cart_item(session: Session, cart_item_id: int, quantity: int, preferred_seat_ids: str) -> Optional[CartItem]:
        """Update cart item quantity and preferred seats"""
        cart_item = session.get(CartItem, cart_item_id)
        if not cart_item:
            return None
        
        # Validate quantity
        bulk_ticket = session.get(BulkTicket, cart_item.bulk_ticket_id)
        if quantity > bulk_ticket.available_seats:
            raise HTTPException(
                status_code=400, 
                detail=f"Only {bulk_ticket.available_seats} seats available"
            )
        
        # Validate preferred seat IDs
        try:
            preferred_seats = json.loads(preferred_seat_ids)
            if not isinstance(preferred_seats, list):
                raise ValueError("Preferred seats must be a list")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid preferred seat IDs format")
        
        cart_item.quantity = quantity
        cart_item.preferred_seat_ids = preferred_seat_ids
        session.add(cart_item)
        session.commit()
        session.refresh(cart_item)
        return cart_item
    
    @staticmethod
    def remove_from_cart(session: Session, cart_item_id: int) -> bool:
        """Remove item from cart"""
        cart_item = session.get(CartItem, cart_item_id)
        if not cart_item:
            return False
        
        session.delete(cart_item)
        session.commit()
        return True
    
    @staticmethod
    def clear_user_cart(session: Session, user_id: int) -> bool:
        """Clear all items from user's cart"""
        cart_items = session.exec(
            select(CartItem).where(CartItem.user_id == user_id)
        ).all()
        
        for item in cart_items:
            session.delete(item)
        
        session.commit()
        return True
