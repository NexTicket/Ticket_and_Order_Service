from fastapi import FastAPI
from database import create_db_and_tables
from Ticket.routers import ticket, venue_event
from Order.routers import order, cart, user, transaction, analytics

app = FastAPI(
    title="Nexticket API", 
    description="Commercial Ticket Service API with Venue, Event, and Order Management", 
    version="2.0.0"
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
            "orders": "/api/orders", 
            "cart": "/api/cart",
            "users": "/api/users",
            "transactions": "/api/transactions",
            "analytics": "/api/analytics"
        }
    }

# Include routers
app.include_router(venue_event.router, prefix="/api/venues-events", tags=["Venues & Events"])
app.include_router(ticket.router, prefix="/api/tickets", tags=["Tickets"])
app.include_router(order.router, prefix="/api/orders", tags=["Orders"])
app.include_router(cart.router, prefix="/api/cart", tags=["Cart"])
app.include_router(user.router, prefix="/api/users", tags=["Users"])
app.include_router(transaction.router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])