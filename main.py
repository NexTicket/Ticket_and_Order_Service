from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import create_db_and_tables
from Ticket.routers import ticket, venue_event
from Order.routers import order, cart, transaction, analytics
from controllers.seat_reservations import router as seat_reservations_router
import os
from dotenv import load_dotenv
from datetime import datetime

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
    allow_origins=[
        "http://localhost:3000",  # Frontend development server
        "http://127.0.0.1:3000",  # Alternative localhost
        os.getenv("FRONTEND_URL", "http://localhost:3000")  # Environment variable
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
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
            "seat_selection": "User preferred seat selection",
            "cart": "Shopping cart with seat preferences",
            "orders": "Order management with QR codes",
            "qr_codes": "Auto-generated QR codes with full details"
        },
        "endpoints": {
            "venues_events": "/api/venues-events",
            "tickets": "/api/tickets",
            "orders": "/api/orders (includes payment functionality)",
            "cart": "/api/cart",
            "users": "/api/users",
            "transactions": "/api/transactions",
            "analytics": "/api/analytics"
        }
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Ticket and Order Service",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }

# Include routers
app.include_router(venue_event.router, prefix="/api/venues-events", tags=["Venues & Events"])
app.include_router(ticket.router, prefix="/api/tickets", tags=["Tickets"])
app.include_router(order.router, prefix="/api/orders", tags=["Orders"])
app.include_router(cart.router, prefix="/api/cart", tags=["Cart"])
app.include_router(transaction.router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(seat_reservations_router, tags=["Seat Reservations"])

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)