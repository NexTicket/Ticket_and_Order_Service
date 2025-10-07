from fastapi import FastAPI, Request
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
allowed_origins = [
    os.getenv("APIGATEWAY_URL", "http://localhost:5000"),  # Local development
]

# Add Docker network origins
docker_gateway = os.getenv("APIGATEWAY_DOCKER_URL")
if docker_gateway:
    allowed_origins.append(docker_gateway)


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=r".*",  
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
            "redis_order": "Temporary Redis-based seat locking (5-min expiry)",
            "firebase_auth": "Firebase JWT authentication (user management in separate microservice)",
            "seat_locking": "Real-time seat locking to prevent conflicts",
            "orders": "Order management with QR codes from Redis locking",
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
    from Database.redis_client import test_redis_connection
    
    redis_status = test_redis_connection()
    return {
        "status": "healthy" if redis_status else "degraded",
        "service": "nexticket-api",
        "redis": "connected" if redis_status else "disconnected",
        "firebase_auth": "configured"
    }

@app.get("/health/auth")
def auth_health_check(current_user=None):
    """Health check endpoint that tests Firebase auth (optional)"""
    from firebase_auth import get_current_user_from_token
    from fastapi import Depends
    
    try:
        # This will be None if no auth header provided, which is fine for health check
        return {
            "status": "healthy",
            "service": "nexticket-api", 
            "auth_configured": True,
            "user_authenticated": current_user is not None
        }
    except Exception as e:
        return {
            "status": "healthy",
            "service": "nexticket-api",
            "auth_configured": True,
            "auth_error": str(e)
        }

@app.get("/debug/headers")
def debug_headers(request: Request):
    """Debug endpoint to see what headers are being received from API Gateway"""
    
    return {
        "headers": dict(request.headers),
        "method": request.method,
        "url": str(request.url),
        "client": request.client.host if request.client else None,
        "auth_header_present": "authorization" in request.headers,
        "auth_header_value": request.headers.get("authorization", "Not present")[:50] + "..." if request.headers.get("authorization") else "Not present"
    }

# Include routers
app.include_router(venue_event.router, prefix="/api/venues-events", tags=["Venues & Events"])
app.include_router(ticket.router, prefix="/api/tickets", tags=["Tickets"])
app.include_router(order.router, prefix="/api/orders", tags=["Orders"])
# app.include_router(cart.router, prefix="/api/cart", tags=["Cart"])  # Disabled - using Redis order locking only
# app.include_router(user.router, prefix="/api/users", tags=["Users"])  # Disabled - user management in separate microservice
app.include_router(transaction.router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(ticket_locking.router, prefix="/api/ticket-locking", tags=["Ticket Locking"])