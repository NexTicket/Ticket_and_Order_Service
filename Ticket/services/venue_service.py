from fastapi import HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from models import Venue, VenueCreate, VenueRead, Event, BulkTicket

class VenueService:
    @staticmethod
    def create_venue(session: Session, venue_data: VenueCreate) -> Venue:
        """Create a new venue"""
        db_venue = Venue.model_validate(venue_data)
        session.add(db_venue)
        session.commit()
        session.refresh(db_venue)
        return db_venue
    
    @staticmethod
    def get_venue(session: Session, venue_id: int) -> Optional[Venue]:
        """Get venue by ID"""
        return session.get(Venue, venue_id)
    
    @staticmethod
    def get_venues(session: Session, skip: int = 0, limit: int = 100) -> List[Venue]:
        """Get all venues with pagination"""
        statement = select(Venue).offset(skip).limit(limit)
        return session.exec(statement).all()
    
    @staticmethod
    def get_venue_events(session: Session, venue_id: int) -> List[Event]:
        """Get all events for a venue"""
        venue = session.get(Venue, venue_id)
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")
        
        statement = select(Event).where(Event.venue_id == venue_id)
        return session.exec(statement).all()
