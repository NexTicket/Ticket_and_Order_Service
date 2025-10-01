"""
Unified Seat Management Service
Handles all seat-related operations: reservation, validation, availability checking
"""

from sqlmodel import Session, select
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import json

from models import (
    SeatReservation, BulkTicket, UserTicket, SeatType, ReservationStatus
)
from services.event_venue_client import fetch_event_details, fetch_venue_details

logger = logging.getLogger(__name__)

class SeatManagementService:
    """Unified service for all seat-related operations"""
    
    @staticmethod
    async def reserve_seats_for_user(
        session: Session,
        event_id: int,
        seat_ids: List[str],
        firebase_uid: str,
        venue_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Step 1: Reserve seats temporarily when user selects them on seat map
        This is the core functionality for the user workflow
        """
        logger.info(f"🎫 Reserving seats for user: event={event_id}, seats={len(seat_ids)}, user={firebase_uid}")
        
        # Validate event exists
        event_details = await fetch_event_details(event_id)
        if not event_details:
            raise ValueError(f"Event {event_id} not found")
        
        # Get venue_id from event if not provided
        if not venue_id:
            venue_id = event_details.get('venue_id', 1)  # Default fallback
        
        # Set reservation expiration (15 minutes)
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        
        reservations = []
        conflicts = []
        
        for seat_id in seat_ids:
            try:
                # Check if seat is available for reservation
                conflict_reason = await SeatManagementService._check_seat_availability(
                    session, event_id, seat_id, firebase_uid
                )
                
                if conflict_reason:
                    conflicts.append({"seatId": seat_id, "reason": conflict_reason})
                    continue
                
                # Create or update reservation
                reservation = await SeatManagementService._create_seat_reservation(
                    session, event_id, seat_id, firebase_uid, expires_at
                )
                
                reservations.append({
                    "id": reservation.id,
                    "seat_id": reservation.seat_id,
                    "status": reservation.status.value,
                    "expires_at": reservation.expires_at.isoformat()
                })
                
                logger.info(f"✅ Reserved seat {seat_id} for user {firebase_uid}")
                
            except Exception as e:
                logger.error(f"❌ Failed to reserve seat {seat_id}: {e}")
                conflicts.append({"seatId": seat_id, "reason": "Reservation failed"})
        
        session.commit()
        
        return {
            "reservations": reservations,
            "conflicts": conflicts,
            "event_id": event_id,
            "venue_id": venue_id,
            "expires_at": expires_at.isoformat()
        }
    
    @staticmethod
    async def _check_seat_availability(
        session: Session, 
        event_id: int, 
        seat_id: str, 
        firebase_uid: str
    ) -> Optional[str]:
        """Check if seat is available for reservation"""
        
        # Check if seat is already sold (permanent reservation)
        sold_ticket = session.exec(
            select(UserTicket).where(
                UserTicket.external_event_id == event_id,
                UserTicket.seat_id == seat_id,
                UserTicket.status == "SOLD"
            )
        ).first()
        
        if sold_ticket:
            return "Seat is already sold"
        
        # Check if seat is reserved by another user (and not expired)
        existing_reservation = session.exec(
            select(SeatReservation).where(
                SeatReservation.external_event_id == event_id,
                SeatReservation.seat_id == seat_id,
                SeatReservation.firebase_uid != firebase_uid,
                SeatReservation.status == ReservationStatus.RESERVED,
                SeatReservation.expires_at > datetime.utcnow()
            )
        ).first()
        
        if existing_reservation:
            return "Already reserved by another user"
        
        return None  # Seat is available
    
    @staticmethod
    async def _create_seat_reservation(
        session: Session,
        event_id: int,
        seat_id: str,
        firebase_uid: str,
        expires_at: datetime
    ) -> SeatReservation:
        """Create or update seat reservation"""
        
        # Check if user already has a reservation for this seat
        existing = session.exec(
            select(SeatReservation).where(
                SeatReservation.external_event_id == event_id,
                SeatReservation.seat_id == seat_id,
                SeatReservation.firebase_uid == firebase_uid
            )
        ).first()
        
        if existing:
            # Update existing reservation
            existing.status = ReservationStatus.RESERVED
            existing.expires_at = expires_at
            existing.updated_at = datetime.utcnow()
            reservation = existing
        else:
            # Create new reservation
            reservation = SeatReservation(
                external_event_id=event_id,
                seat_id=seat_id,
                firebase_uid=firebase_uid,
                status=ReservationStatus.RESERVED,
                expires_at=expires_at
            )
            session.add(reservation)
        
        session.flush()  # Get the ID
        return reservation
    
    @staticmethod
    def get_seat_reservations_for_event(
        session: Session,
        event_id: int,
        firebase_uid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get all active reservations for an event"""
        
        # Get all active reservations
        reservations = session.exec(
            select(SeatReservation).where(
                SeatReservation.external_event_id == event_id,
                SeatReservation.status.in_([ReservationStatus.RESERVED, ReservationStatus.CONFIRMED]),
                SeatReservation.expires_at > datetime.utcnow()
            )
        ).all()
        
        # Get sold seats
        sold_tickets = session.exec(
            select(UserTicket).where(
                UserTicket.external_event_id == event_id,
                UserTicket.status == "SOLD"
            )
        ).all()
        
        # Categorize seats
        reserved_by_others = []
        my_reservations = []
        sold_seats = [ticket.seat_id for ticket in sold_tickets]
        
        for reservation in reservations:
            if firebase_uid and reservation.firebase_uid == firebase_uid:
                my_reservations.append(reservation.seat_id)
            else:
                reserved_by_others.append(reservation.seat_id)
        
        return {
            "reservedSeats": reserved_by_others,  # Reserved by other users
            "myReservations": my_reservations,    # Reserved by current user
            "soldSeats": sold_seats,              # Permanently sold seats
            "totalReservations": len(reservations)
        }
    
    @staticmethod
    async def get_or_create_bulk_ticket(
        session: Session,
        event_id: int,
        venue_id: int,
        seat_type: SeatType,
        price: float
    ) -> BulkTicket:
        """Get existing or create new bulk ticket for seat group"""
        
        # Try to find existing bulk ticket
        bulk_ticket = session.exec(
            select(BulkTicket).where(
                BulkTicket.external_event_id == event_id,
                BulkTicket.external_venue_id == venue_id,
                BulkTicket.seat_type == seat_type
            )
        ).first()
        
        if not bulk_ticket:
            # Create new bulk ticket
            venue_details = await fetch_venue_details(venue_id)
            default_capacity = venue_details.get('capacity', 1000) if venue_details else 1000
            
            bulk_ticket = BulkTicket(
                external_event_id=event_id,
                external_venue_id=venue_id,
                seat_type=seat_type,
                price=price,
                total_seats=default_capacity,
                available_seats=default_capacity,
                seat_prefix=seat_type.value[:3].upper()
            )
            session.add(bulk_ticket)
            session.flush()
            
            logger.info(f"📋 Created bulk ticket {bulk_ticket.id} for event {event_id}, type {seat_type}")
        
        return bulk_ticket
    
    @staticmethod
    def confirm_reservations_for_order(session: Session, firebase_uid: str, order_id: int):
        """Confirm seat reservations when order is completed - makes them permanently reserved"""
        reservations = session.exec(
            select(SeatReservation).where(
                SeatReservation.firebase_uid == firebase_uid,
                SeatReservation.status == ReservationStatus.RESERVED
            )
        ).all()
        
        confirmed_count = 0
        for reservation in reservations:
            reservation.status = ReservationStatus.CONFIRMED
            reservation.order_id = order_id
            reservation.updated_at = datetime.utcnow()
            confirmed_count += 1
        
        session.commit()
        logger.info(f"✅ Confirmed {confirmed_count} seat reservations for order {order_id}")
        return confirmed_count

    @staticmethod
    def release_expired_reservations(session: Session):
        """Release expired reservations - makes seats available again"""
        expired_reservations = session.exec(
            select(SeatReservation).where(
                SeatReservation.expires_at <= datetime.utcnow(),
                SeatReservation.status == ReservationStatus.RESERVED
            )
        ).all()

        expired_count = 0
        for reservation in expired_reservations:
            reservation.status = ReservationStatus.EXPIRED
            reservation.updated_at = datetime.utcnow()
            expired_count += 1

        session.commit()
        logger.info(f"🧹 Released {expired_count} expired reservations")
        return expired_count

    @staticmethod
    def release_seats_for_user(session: Session, event_id: int, seat_ids: list, firebase_uid: str):
        """Release specific seat reservations for a user (cancel reservations)"""
        reservations_to_cancel = session.exec(
            select(SeatReservation).where(
                SeatReservation.external_event_id == event_id,
                SeatReservation.seat_id.in_(seat_ids),
                SeatReservation.firebase_uid == firebase_uid,
                SeatReservation.status == ReservationStatus.RESERVED
            )
        ).all()

        cancelled_count = 0
        for reservation in reservations_to_cancel:
            reservation.status = ReservationStatus.CANCELLED
            reservation.updated_at = datetime.utcnow()
            cancelled_count += 1

        session.commit()
        logger.info(f"🔓 Released {cancelled_count} seat reservations for user {firebase_uid}")
        return cancelled_count
    
    @staticmethod
    def release_expired_reservations(session: Session) -> int:
        """Clean up expired reservations"""
        expired_reservations = session.exec(
            select(SeatReservation).where(
                SeatReservation.expires_at <= datetime.utcnow(),
                SeatReservation.status == ReservationStatus.RESERVED
            )
        ).all()
        
        count = len(expired_reservations)
        for reservation in expired_reservations:
            reservation.status = ReservationStatus.EXPIRED
        
        session.commit()
        logger.info(f"🧹 Released {count} expired reservations")
        return count