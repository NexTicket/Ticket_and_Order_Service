"""
Unified Cart Management Service
Handles: Add to cart, cart operations, cart clearing
"""

from sqlmodel import Session, select
from typing import List, Dict, Any
import json
import logging

from models import CartItem, BulkTicket, SeatType
from services.seat_management_service import SeatManagementService

logger = logging.getLogger(__name__)

class CartManagementService:
    """Unified service for cart operations"""
    
    @staticmethod
    async def add_reserved_seats_to_cart(
        session: Session,
        firebase_uid: str,
        event_id: int,
        venue_id: int,
        seats_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Step 2: Add reserved seats to cart
        This happens when user clicks "Add to Cart" after selecting seats
        """
        logger.info(f"🛒 Adding {len(seats_data)} seats to cart for user {firebase_uid}")
        
        if not seats_data:
            raise ValueError("No seat data provided")
        
        # Group seats by type for efficient bulk ticket management
        seats_by_type = {}
        for seat in seats_data:
            seat_type = seat.get("seatType", "REGULAR")
            if seat_type not in seats_by_type:
                seats_by_type[seat_type] = []
            seats_by_type[seat_type].append(seat)
        
        cart_items_created = []
        total_amount = 0
        
        # Process each seat type group
        for seat_type_str, seats_group in seats_by_type.items():
            try:
                # Convert to enum
                seat_type = SeatType(seat_type_str)
            except ValueError:
                seat_type = SeatType.REGULAR
            
            # Calculate average price for this group
            avg_price = sum(seat.get("price", 0) for seat in seats_group) / len(seats_group)
            
            # Get or create bulk ticket
            bulk_ticket = await SeatManagementService.get_or_create_bulk_ticket(
                session, event_id, venue_id, seat_type, avg_price
            )
            
            # Extract seat IDs
            seat_ids = [seat["seatId"] for seat in seats_group]
            
            # Create cart item
            cart_item = CartItem(
                firebase_uid=firebase_uid,
                bulk_ticket_id=bulk_ticket.id,
                preferred_seat_ids=json.dumps(seat_ids),
                quantity=len(seats_group)
            )
            
            session.add(cart_item)
            session.flush()  # Get the ID
            
            item_total = bulk_ticket.price * len(seats_group)
            total_amount += item_total
            
            cart_items_created.append({
                "cart_item_id": cart_item.id,
                "bulk_ticket_id": bulk_ticket.id,
                "seat_type": seat_type_str,
                "seat_ids": seat_ids,
                "quantity": len(seats_group),
                "price_per_item": bulk_ticket.price,
                "total_price": item_total,
                "event_id": event_id,
                "venue_id": venue_id
            })
            
            logger.info(f"✅ Created cart item: {len(seats_group)} {seat_type_str} seats")
        
        session.commit()
        
        logger.info(f"🎯 Cart updated: {len(cart_items_created)} items, total: ${total_amount}")
        
        return {
            "cart_items": cart_items_created,
            "total_items": sum(item["quantity"] for item in cart_items_created),
            "total_amount": total_amount,
            "event_id": event_id,
            "venue_id": venue_id
        }
    
    @staticmethod
    def get_user_cart_summary(
        session: Session,
        firebase_uid: str
    ) -> Dict[str, Any]:
        """Get user's current cart summary"""
        
        cart_items = session.exec(
            select(CartItem).where(CartItem.firebase_uid == firebase_uid)
        ).all()
        
        if not cart_items:
            return {
                "cart_items": [],
                "total_items": 0,
                "total_amount": 0,
                "is_empty": True
            }
        
        items_summary = []
        total_amount = 0
        total_quantity = 0
        
        for cart_item in cart_items:
            bulk_ticket = session.get(BulkTicket, cart_item.bulk_ticket_id)
            if not bulk_ticket:
                continue
            
            item_total = bulk_ticket.price * cart_item.quantity
            total_amount += item_total
            total_quantity += cart_item.quantity
            
            # Parse seat IDs
            try:
                seat_ids = json.loads(cart_item.preferred_seat_ids) if cart_item.preferred_seat_ids else []
            except json.JSONDecodeError:
                seat_ids = []
            
            items_summary.append({
                "cart_item_id": cart_item.id,
                "bulk_ticket_id": bulk_ticket.id,
                "event_id": bulk_ticket.external_event_id,
                "venue_id": bulk_ticket.external_venue_id,
                "seat_type": bulk_ticket.seat_type.value,
                "seat_ids": seat_ids,
                "quantity": cart_item.quantity,
                "price_per_item": bulk_ticket.price,
                "total_price": item_total
            })
        
        return {
            "cart_items": items_summary,
            "total_items": total_quantity,
            "total_amount": total_amount,
            "is_empty": False
        }
    
    @staticmethod
    def clear_user_cart(session: Session, firebase_uid: str) -> int:
        """
        Clear user's cart (called after successful order completion)
        """
        logger.info(f"🧹 Clearing cart for user {firebase_uid}")
        
        cart_items = session.exec(
            select(CartItem).where(CartItem.firebase_uid == firebase_uid)
        ).all()
        
        count = len(cart_items)
        for item in cart_items:
            session.delete(item)
        
        session.commit()
        logger.info(f"✅ Cleared {count} items from cart")
        return count
    
    @staticmethod
    def remove_cart_item(
        session: Session,
        firebase_uid: str,
        cart_item_id: int
    ) -> bool:
        """Remove specific item from cart"""
        
        cart_item = session.exec(
            select(CartItem).where(
                CartItem.id == cart_item_id,
                CartItem.firebase_uid == firebase_uid
            )
        ).first()
        
        if not cart_item:
            return False
        
        session.delete(cart_item)
        session.commit()
        
        logger.info(f"🗑️ Removed cart item {cart_item_id}")
        return True