from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from models import (
    CartItem, CartItemCreate, CartItemRead, CartItemUpdate,
    BulkTicket, CartSummary
)
import json
import httpx
import os

class CartService:
    EVENT_VENUE_SERVICE_URL = os.getenv("EVENT_VENUE_SERVICE_URL", "http://localhost:4000")
    
    @staticmethod
    async def _fetch_event_venue_data(bulk_ticket: BulkTicket) -> Dict[str, Any]:
        """Fetch event and venue data from Event_and_Venue_Service"""
        event_data = None
        venue_data = None
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Fetch event data
                if bulk_ticket.external_event_id:
                    try:
                        event_response = await client.get(
                            f"{CartService.EVENT_VENUE_SERVICE_URL}/api/events/{bulk_ticket.external_event_id}"
                        )
                        if event_response.status_code == 200:
                            event_data = event_response.json()
                    except Exception as e:
                        print(f"Error fetching event {bulk_ticket.external_event_id}: {e}")
                
                # Fetch venue data
                if bulk_ticket.external_venue_id:
                    try:
                        venue_response = await client.get(
                            f"{CartService.EVENT_VENUE_SERVICE_URL}/api/venues/{bulk_ticket.external_venue_id}"
                        )
                        if venue_response.status_code == 200:
                            venue_data = venue_response.json()
                    except Exception as e:
                        print(f"Error fetching venue {bulk_ticket.external_venue_id}: {e}")
        
        except Exception as e:
            print(f"Error connecting to Event_and_Venue_Service: {e}")
        
        return {
            "event": event_data,
            "venue": venue_data
        }
    
    @staticmethod
    def add_to_cart(session: Session, cart_data: CartItemCreate) -> CartItem:
        """Add item to cart with preferred seat selection using Firebase UID"""
        # Note: Firebase UID validity is handled by the frontend/auth layer
        
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
        
        # Check if item already exists in cart for this Firebase user and bulk ticket
        existing_cart_item = session.exec(
            select(CartItem).where(
                CartItem.firebase_uid == cart_data.firebase_uid,
                CartItem.bulk_ticket_id == cart_data.bulk_ticket_id
            )
        ).first()
        
        if existing_cart_item:
            # Update existing item
            existing_cart_item.quantity = cart_data.quantity
            existing_cart_item.preferred_seat_ids = cart_data.preferred_seat_ids
            existing_cart_item.updated_at = datetime.now(timezone.utc)
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
        """Get all cart items for a user (deprecated - use Firebase UID version)"""
        statement = select(CartItem).where(CartItem.user_id == user_id)
        return session.exec(statement).all()

    @staticmethod
    def get_user_cart_by_firebase_uid(session: Session, firebase_uid: str) -> List[CartItem]:
        """Get all cart items for a Firebase user"""
        statement = select(CartItem).where(CartItem.firebase_uid == firebase_uid)
        return session.exec(statement).all()
    
    @staticmethod
    def get_cart_summary(session: Session, user_id: int) -> CartSummary:
        """Get cart summary with total items and amount (deprecated - use Firebase UID version)"""
        cart_items = CartService.get_user_cart(session, user_id)
        
        total_items = sum(item.quantity for item in cart_items)
        total_amount = 0

    @staticmethod
    async def get_cart_summary_by_firebase_uid(session: Session, firebase_uid: str) -> CartSummary:
        """Get cart summary with total items and amount for Firebase user"""
        cart_items = CartService.get_user_cart_by_firebase_uid(session, firebase_uid)
        
        total_items = sum(item.quantity for item in cart_items)
        total_amount = 0
        
        cart_reads = []
        for item in cart_items:
            bulk_ticket = session.get(BulkTicket, item.bulk_ticket_id)
            if bulk_ticket:
                total_amount += bulk_ticket.price * item.quantity
                
                # Fetch event and venue data
                event_venue_data = await CartService._fetch_event_venue_data(bulk_ticket)
                
                # Create a CartItemRead with enhanced bulk ticket data
                cart_item_dict = item.model_dump()
                bulk_ticket_dict = bulk_ticket.model_dump()
                
                # Add event and venue data to bulk ticket
                if event_venue_data["event"]:
                    bulk_ticket_dict["event"] = event_venue_data["event"]
                if event_venue_data["venue"]:
                    bulk_ticket_dict["venue"] = event_venue_data["venue"]
                
                cart_item_dict['bulk_ticket'] = bulk_ticket_dict
                cart_reads.append(cart_item_dict)
            else:
                # If bulk ticket not found, still include the cart item
                cart_reads.append(item.model_dump())
        
        return CartSummary(
            total_items=total_items,
            total_amount=total_amount,
            items=cart_reads
        )
    
    @staticmethod
    def update_cart_item(session: Session, cart_item_id: int, update_data: CartItemUpdate) -> Optional[CartItem]:
        """Update cart item quantity and preferred seats"""
        cart_item = session.get(CartItem, cart_item_id)
        if not cart_item:
            return None
        
        # Only update fields that are provided
        if update_data.quantity is not None:
            # Validate quantity
            bulk_ticket = session.get(BulkTicket, cart_item.bulk_ticket_id)
            if update_data.quantity > bulk_ticket.available_seats:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Only {bulk_ticket.available_seats} seats available"
                )
            cart_item.quantity = update_data.quantity
        
        if update_data.preferred_seat_ids is not None:
            # Validate preferred seat IDs
            try:
                preferred_seats = json.loads(update_data.preferred_seat_ids)
                if not isinstance(preferred_seats, list):
                    raise ValueError("Preferred seats must be a list")
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid preferred seat IDs format")
            
            cart_item.preferred_seat_ids = update_data.preferred_seat_ids
        
        # Update the updated_at timestamp
        cart_item.updated_at = datetime.now(timezone.utc)
        
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
        """Clear all items from user's cart (deprecated - use Firebase UID version)"""
        cart_items = session.exec(
            select(CartItem).where(CartItem.user_id == user_id)
        ).all()
        
        for item in cart_items:
            session.delete(item)
        
        session.commit()
        return True

    @staticmethod
    def clear_user_cart_by_firebase_uid(session: Session, firebase_uid: str) -> bool:
        """Clear all items from Firebase user's cart"""
        cart_items = session.exec(
            select(CartItem).where(CartItem.firebase_uid == firebase_uid)
        ).all()
        
        for item in cart_items:
            session.delete(item)
        
        session.commit()
        return True
