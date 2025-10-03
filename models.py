from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum
import uuid
import json

class SeatType(str, Enum):
    VIP = "VIP"
    REGULAR = "REGULAR"

class TicketStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    CANCELLED = "cancelled"

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class TransactionStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


# Venue Model
class VenueBase(SQLModel):
    name: str = Field(index=True)
    address: str
    city: str
    capacity: int = Field(ge=1)
    description: Optional[str] = None

class Venue(VenueBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    events: List["Event"] = Relationship(back_populates="venue")
    bulk_tickets: List["BulkTicket"] = Relationship(back_populates="venue")

class VenueCreate(VenueBase):
    pass

class VenueRead(VenueBase):
    id: int
    created_at: datetime

# Event Model
class EventBase(SQLModel):
    name: str = Field(index=True)
    description: Optional[str] = None
    event_date: datetime
    venue_id: int = Field(foreign_key="venue.id")

class Event(EventBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    venue: Venue = Relationship(back_populates="events")
    bulk_tickets: List["BulkTicket"] = Relationship(back_populates="event")

class EventCreate(EventBase):
    pass

class EventRead(EventBase):
    id: int
    created_at: datetime

# BulkTicket Model - Created by organizers
class BulkTicketBase(SQLModel):
    event_id: int = Field(foreign_key="event.id")
    venue_id: int = Field(foreign_key="venue.id")
    seat_type: SeatType
    price: float = Field(ge=0)
    total_seats: int = Field(ge=1)
    available_seats: int = Field(ge=0)
    seat_prefix: str  # e.g., "A", "B", "VIP" - used to generate seat IDs

class BulkTicket(BulkTicketBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    # Relationships
    event: Event = Relationship(back_populates="bulk_tickets")
    venue: Venue = Relationship(back_populates="bulk_tickets")
    user_tickets: List["UserTicket"] = Relationship(back_populates="bulk_ticket")

class BulkTicketCreate(BulkTicketBase):
    pass

class BulkTicketRead(BulkTicketBase):
    id: int
    created_at: datetime

class BulkTicketUpdate(SQLModel):
    price: Optional[float] = None
    available_seats: Optional[int] = None

# Redis Cart Models (for temporary cart data structure)
class RedisCartItem(SQLModel):
    bulk_ticket_id: int
    seat_ids: List[str]  # Specific seat IDs locked for this item
    quantity: int
    price_per_seat: float

class CreateOrderFromRedisRequest(SQLModel):
    payment_method: str = "stripe"
    
class OrderSummaryResponse(SQLModel):
    cart_id: str
    user_id: str 
    total_seats: int
    total_amount: float
    items: List[RedisCartItem]
    expires_at: datetime
    remaining_seconds: int
    
# UserOrder Model - After purchase
class UserOrderBase(SQLModel):
    firebase_uid: str = Field(index=True)  # Firebase UID instead of user_id
    total_amount: float = Field(ge=0)
    status: OrderStatus = OrderStatus.PENDING
    notes: Optional[str] = None

class UserOrder(UserOrderBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_reference: str = Field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:8].upper()}", unique=True, index=True)
    payment_intent_id: Optional[str] = Field(default=None, unique=True)
    stripe_payment_id: Optional[str] = Field(default=None)
    service_fee: float = Field(default=0.0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Relationships
    user_tickets: List["UserTicket"] = Relationship(back_populates="order")
    transactions: List["Transaction"] = Relationship(back_populates="order")

class UserOrderCreate(UserOrderBase):
    pass

class UserOrderRead(UserOrderBase):
    id: int
    order_reference: str
    payment_intent_id: Optional[str] = None
    stripe_payment_id: Optional[str] = None
    service_fee: float
    created_at: datetime
    completed_at: Optional[datetime] = None

class UserOrderUpdate(SQLModel):
    status: Optional[OrderStatus] = None
    notes: Optional[str] = None

# UserTicket Model - Individual tickets owned by users
class UserTicketBase(SQLModel):
    order_id: int = Field(foreign_key="userorder.id")
    bulk_ticket_id: int = Field(foreign_key="bulkticket.id")
    firebase_uid: str = Field(index=True)  # Firebase UID instead of user_id
    seat_id: str = Field(index=True)  # Unique seat identifier like "A1", "B25", "VIP001"
    price_paid: float = Field(ge=0)
    status: TicketStatus = TicketStatus.SOLD

class UserTicket(UserTicketBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    qr_code_data: str = Field(default="", index=True)  # Will be generated with full details
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    order: UserOrder = Relationship(back_populates="user_tickets")
    bulk_ticket: BulkTicket = Relationship(back_populates="user_tickets")

class UserTicketCreate(UserTicketBase):
    pass

class UserTicketRead(UserTicketBase):
    id: int
    qr_code_data: str
    created_at: datetime

# Transaction Model
class TransactionBase(SQLModel):
    order_id: int = Field(foreign_key="userorder.id")
    amount: float = Field(ge=0)
    payment_method: str
    transaction_reference: Optional[str] = None
    status: TransactionStatus = TransactionStatus.PENDING

class Transaction(TransactionBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: str = Field(default_factory=lambda: f"TXN-{uuid.uuid4().hex[:8].upper()}", unique=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    # Relationships
    order: UserOrder = Relationship(back_populates="transactions")

class TransactionCreate(TransactionBase):
    pass

class TransactionRead(TransactionBase):
    id: int
    transaction_id: str
    created_at: datetime

class TransactionUpdate(SQLModel):
    status: Optional[TransactionStatus] = None
    transaction_reference: Optional[str] = None

# Ticket Locking Models (Redis-based temporary cart)

class LockSeatsRequest(SQLModel):
    seat_ids: List[str]
    event_id: int
    bulk_ticket_id: Optional[int] = None  # Optional for additional validation

class LockSeatsResponse(SQLModel):
    message: str
    cart_id: str
    user_id: str
    seat_ids: List[str]
    event_id: int
    expires_in_seconds: int
    expires_at: datetime

class UnlockSeatsRequest(SQLModel):
    cart_id: Optional[str] = None  # If not provided, unlock all user's locked seats
    seat_ids: Optional[List[str]] = None  # If provided, unlock only these seats

class UnlockSeatsResponse(SQLModel):
    message: str
    unlocked_seat_ids: List[str]

class GetLockedSeatsResponse(SQLModel):
    cart_id: str
    user_id: str
    seat_ids: List[str]
    event_id: int
    status: str
    expires_at: datetime
    remaining_seconds: int

class SeatAvailabilityRequest(SQLModel):
    event_id: int
    seat_ids: List[str]

class SeatAvailabilityResponse(SQLModel):
    event_id: int
    available_seats: List[str]
    locked_seats: List[dict]  # List of {seat_id, locked_by_user_id, expires_at}
    unavailable_seats: List[str]  # Already sold/reserved in main DB

class ExtendLockRequest(SQLModel):
    cart_id: str
    additional_seconds: Optional[int] = 300  # Default 5 minutes extension

class ExtendLockResponse(SQLModel):
    message: str
    cart_id: str
    new_expires_at: datetime
    total_remaining_seconds: int

# Helper Models for API responses

class TicketWithDetails(SQLModel):
    id: int
    seat_id: str
    qr_code_data: str
    event_name: str
    venue_name: str
    event_date: datetime
    seat_type: SeatType
    price_paid: float
    status: TicketStatus

# Stripe Payment Models
class CreatePaymentIntentRequest(SQLModel):
    amount: int  # Amount in cents
    orderId: int

class CreatePaymentIntentResponse(SQLModel):
    client_secret: str
    payment_intent_id: str

class CompleteOrderRequest(SQLModel):
    paymentIntentId: str

class UpdateOrderStatusRequest(SQLModel):
    status: OrderStatus