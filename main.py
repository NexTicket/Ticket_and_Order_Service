from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_db_and_tables
from Ticket.routers import ticket, venue_event
from Order.routers import order, transaction, analytics, ticket_locking
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Nexticket API", 
    description="Commercial Ticket Service API with Tickets and Order Management", 
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("APIGATEWAY_URL", "http://localhost:5000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables on startup
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

@app.get("/")
def read_root():
    return {
        "message": "Welcome to Nexticket API - Commercial Ticketing System",
        "version": "2.0.0",
        "docs": "/docs",
        "features": {
            "venues": "Venue management",
            "events": "Event management with date/time",
            "bulk_tickets": "Bulk ticket creation by organizers",
            "redis_cart": "Temporary Redis-based seat locking (5-min expiry)",
            "firebase_auth": "Firebase JWT authentication (user management in separate microservice)",
            "seat_locking": "Real-time seat locking to prevent conflicts",
            "orders": "Order management with QR codes from Redis cart",
            "qr_codes": "Auto-generated QR codes with full details",
            "stripe_payment": "Stripe payment processing"
        },
        "endpoints": {
            "venues_events": "/api/venues-events",
            "tickets": "/api/tickets",
            "orders": "/api/orders", 
            "ticket_locking": "/api/ticket-locking",
            "transactions": "/api/transactions",
            "analytics": "/api/analytics"
        }
    }

@app.get("/health")
def health_check():
    """Health check endpoint for Docker and load balancers"""
    return {"status": "healthy", "service": "nexticket-api"}

# Include routers
app.include_router(venue_event.router, prefix="/api/venues-events", tags=["Venues & Events"])
app.include_router(ticket.router, prefix="/api/tickets", tags=["Tickets"])
app.include_router(order.router, prefix="/api/orders", tags=["Orders"])
# app.include_router(cart.router, prefix="/api/cart", tags=["Cart"])  # Disabled - using Redis cart only
# app.include_router(user.router, prefix="/api/users", tags=["Users"])  # Disabled - user management in separate microservice
app.include_router(transaction.router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(ticket_locking.router, prefix="/api/ticket-locking", tags=["Ticket Locking"])