"""
Inter-service communication utility for Ticket_and_Order_Service
Handles communication with Event_and_Venue_Service for event and venue data
"""
import os
import httpx
import logging
from typing import Optional, Dict, Any
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EventVenueServiceClient:
    def __init__(self):
        self.base_url = os.getenv("EVENT_VENUE_SERVICE_URL", "http://localhost:3001")
        self.api_base = f"{self.base_url}/api"
        logger.info(f"🔧 EventVenueServiceClient initialized with base_url: {self.base_url}")
        logger.info(f"🔧 API base URL: {self.api_base}")
        
    async def get_event_details(self, event_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch event details from Event_and_Venue_Service
        """
        url = f"{self.api_base}/events/geteventbyid/{event_id}"
        logger.info(f"🌐 Fetching event details from: {url}")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                logger.info(f"📥 Response from {url}: Status {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"✅ Successfully fetched event {event_id}: {data.get('data', {}).get('title', 'Unknown')}")
                    return data.get('data')  # Extract the data field from response
                else:
                    response_text = response.text
                    logger.error(f"❌ Failed to fetch event {event_id}: {response.status_code} - {response_text}")
                    return None
        except Exception as e:
            logger.error(f"🚨 Exception fetching event {event_id} from {url}: {e}")
            return None
    
    async def get_venue_details(self, venue_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch venue details from Event_and_Venue_Service
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_base}/venues/{venue_id}")
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to fetch venue {venue_id}: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching venue {venue_id}: {e}")
            return None
    
    async def get_venue_seat_map(self, venue_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch venue seat map from Event_and_Venue_Service
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_base}/venues/{venue_id}/seatmap")
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to fetch seat map for venue {venue_id}: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching seat map for venue {venue_id}: {e}")
            return None
    
    async def get_event_seat_availability(self, event_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch event seat availability from Event_and_Venue_Service
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_base}/events/{event_id}/seats/availability")
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to fetch seat availability for event {event_id}: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching seat availability for event {event_id}: {e}")
            return None

# Global client instance
event_venue_client = EventVenueServiceClient()

# Convenience functions for controllers
async def fetch_event_details(event_id: int) -> Optional[Dict[str, Any]]:
    """Fetch event details - convenience function"""
    return await event_venue_client.get_event_details(event_id)

async def fetch_venue_details(venue_id: int) -> Optional[Dict[str, Any]]:
    """Fetch venue details - convenience function"""
    return await event_venue_client.get_venue_details(venue_id)

async def fetch_venue_seat_map(venue_id: int) -> Optional[Dict[str, Any]]:
    """Fetch venue seat map - convenience function"""
    return await event_venue_client.get_venue_seat_map(venue_id)

async def fetch_event_seat_availability(event_id: int) -> Optional[Dict[str, Any]]:
    """Fetch event seat availability - convenience function"""
    return await event_venue_client.get_event_seat_availability(event_id)