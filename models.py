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

# User Model
class UserBase(SQLModel):
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    full_name: str
    phone_number: Optional[str] = None
    is_active: bool = True

class User(UserBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    # Relationships
    orders: List["UserOrder"] = Relationship(back_populates="user")
    cart_items: List["CartItem"] = Relationship(back_populates="user")

class UserCreate(UserBase):
    pass

class UserRead(UserBase):
    id: int
    created_at: datetime

class UserUpdate(SQLModel):
    username: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    is_active: Optional[bool] = None

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
    cart_items: List["CartItem"] = Relationship(back_populates="bulk_ticket")
    user_tickets: List["UserTicket"] = Relationship(back_populates="bulk_ticket")

class BulkTicketCreate(BulkTicketBase):
    pass

class BulkTicketRead(BulkTicketBase):
    id: int
    created_at: datetime

class BulkTicketUpdate(SQLModel):
    price: Optional[float] = None
    available_seats: Optional[int] = None

# Cart Model - Items user wants to buy
class CartItemBase(SQLModel):
    user_id: int = Field(foreign_key="user.id")
    bulk_ticket_id: int = Field(foreign_key="bulkticket.id")
    preferred_seat_ids: str  # JSON string of preferred seat IDs
    quantity: int = Field(ge=1)

class CartItem(CartItemBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    # Relationships
    user: User = Relationship(back_populates="cart_items")
    bulk_ticket: BulkTicket = Relationship(back_populates="cart_items")
    
#     {
#   "user_id": 1,
#   "bulk_ticket_id": 1,
#   "preferred_seat_ids": "[\"SM1\", \"SM2\", \"SM3\"]",
#   "quantity": 3,
#   "id": 1,
#   "created_at": "2025-09-05T14:07:14.913187"
# }

class CartItemCreate(CartItemBase):
    pass

class CartItemRead(CartItemBase):
    id: int
    created_at: datetime

class CartItemUpdate(SQLModel):
    quantity: Optional[int] = Field(None, ge=1)
    preferred_seat_ids: Optional[str] = None
    
# UserOrder Model - After purchase
class UserOrderBase(SQLModel):
    user_id: int = Field(foreign_key="user.id")
    total_amount: float = Field(ge=0)
    status: OrderStatus = OrderStatus.PENDING
    notes: Optional[str] = None

class UserOrder(UserOrderBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_reference: str = Field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:8].upper()}", unique=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    # Relationships
    user: User = Relationship(back_populates="orders")
    user_tickets: List["UserTicket"] = Relationship(back_populates="order")
    transactions: List["Transaction"] = Relationship(back_populates="order")

class UserOrderCreate(UserOrderBase):
    pass

class UserOrderRead(UserOrderBase):
    id: int
    order_reference: str
    created_at: datetime

class UserOrderUpdate(SQLModel):
    status: Optional[OrderStatus] = None
    notes: Optional[str] = None

# UserTicket Model - Individual tickets owned by users
class UserTicketBase(SQLModel):
    order_id: int = Field(foreign_key="userorder.id")
    bulk_ticket_id: int = Field(foreign_key="bulkticket.id")
    user_id: int = Field(foreign_key="user.id")
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
    user: User = Relationship()

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

# Helper Models for API responses
class CartSummary(SQLModel):
    total_items: int
    total_amount: float
    items: List[CartItemRead]

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