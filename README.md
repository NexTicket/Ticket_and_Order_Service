# Nexticket API

A comprehensive ticket service API built with FastAPI and SQLModel, featuring order management, cart functionality, user management, and analytics.

## Features

### Core Functionality
- **Ticket Management**: Create, read, update, delete tickets with status tracking
- **Order Management**: Complete order lifecycle from creation to completion
- **Shopping Cart**: Add tickets to cart, manage quantities, checkout
- **User Management**: User registration, profile management, order history
- **Transaction Processing**: Payment processing and transaction tracking
- **Analytics**: Comprehensive reporting and analytics dashboard

### Database Models
- **User**: User accounts and profiles
- **Ticket**: Event tickets with availability tracking
- **Order**: Order management with status tracking
- **OrderItem**: Individual items within orders
- **Cart**: Shopping cart functionality
- **Transaction**: Payment and transaction records
- **UserOrder**: Additional user-order relationships

## Project Structure

```
Ticket_Service/
├── main.py                 # FastAPI application entry point
├── database.py             # Database configuration and session management
├── models.py               # SQLModel database models
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── Ticket/                # Ticket management module
│   ├── __init__.py
│   ├── routers/
│   │   ├── __init__.py
│   │   └── ticket.py      # Ticket CRUD operations
│   └── services/
│       └── __init__.py
└── Order/                 # Order management module
    ├── __init__.py
    ├── routers/
    │   ├── __init__.py
    │   ├── order.py       # Order CRUD operations
    │   ├── cart.py        # Cart management
    │   ├── user.py        # User management
    │   ├── transaction.py # Transaction management
    │   └── analytics.py   # Analytics and reporting
    └── services/
        ├── __init__.py
        └── order_service.py # Complex order business logic
```

## Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd Ticket_Service
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env file with your configuration
```

5. **Run the application**
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the application is running, you can access:
- **Interactive API docs**: `http://localhost:8000/docs`
- **Alternative docs**: `http://localhost:8000/redoc`

## API Endpoints

### Tickets (`/api/tickets`)
- `POST /` - Create ticket
- `GET /` - List tickets with filtering
- `GET /{ticket_id}` - Get specific ticket
- `PUT /{ticket_id}` - Update ticket
- `DELETE /{ticket_id}` - Delete ticket
- `PATCH /{ticket_id}/status` - Update ticket status
- `GET /search/by-event` - Search tickets by criteria

### Orders (`/api/orders`)
- `POST /` - Create order
- `GET /` - List orders with filtering
- `GET /{order_id}` - Get specific order
- `PUT /{order_id}` - Update order
- `DELETE /{order_id}` - Delete order
- `POST /{order_id}/items` - Add item to order
- `GET /{order_id}/items` - Get order items
- `POST /from-cart/{user_id}` - Create order from cart
- `PATCH /{order_id}/status` - Update order status
- `POST /{order_id}/cancel` - Cancel order

### Cart (`/api/cart`)
- `POST /` - Add item to cart
- `GET /user/{user_id}` - Get user's cart
- `PUT /{cart_item_id}` - Update cart item
- `DELETE /{cart_item_id}` - Remove from cart
- `DELETE /user/{user_id}/clear` - Clear user's cart
- `GET /user/{user_id}/total` - Get cart total

### Users (`/api/users`)
- `POST /` - Create user
- `GET /` - List users
- `GET /{user_id}` - Get specific user
- `GET /username/{username}` - Get user by username
- `PUT /{user_id}` - Update user
- `DELETE /{user_id}` - Delete user
- `PATCH /{user_id}/deactivate` - Deactivate user
- `PATCH /{user_id}/activate` - Activate user

### Transactions (`/api/transactions`)
- `POST /` - Create transaction
- `GET /` - List transactions
- `GET /{transaction_id}` - Get specific transaction
- `PUT /{transaction_id}` - Update transaction
- `PATCH /{transaction_id}/status` - Update transaction status
- `POST /{transaction_id}/refund` - Process refund
- `GET /order/{order_id}` - Get order transactions

### Analytics (`/api/analytics`)
- `GET /dashboard` - Dashboard analytics
- `GET /sales` - Sales analytics
- `GET /revenue` - Revenue analytics
- `GET /users` - User analytics
- `GET /tickets` - Ticket analytics

## Usage Examples

### Create a User
```bash
curl -X POST "http://localhost:8000/api/users/" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "phone_number": "+1234567890"
  }'
```

### Create a Ticket
```bash
curl -X POST "http://localhost:8000/api/tickets/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Concert 2024",
    "event_description": "Amazing concert event",
    "event_date": "2024-12-25T20:00:00",
    "venue": "Main Arena",
    "price": 99.99,
    "available_quantity": 100,
    "total_quantity": 100,
    "category": "VIP"
  }'
```

### Add to Cart
```bash
curl -X POST "http://localhost:8000/api/cart/" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "ticket_id": 1,
    "quantity": 2
  }'
```

### Create Order from Cart
```bash
curl -X POST "http://localhost:8000/api/orders/from-cart/1"
```

## Database Models

### Enums
- **TicketStatus**: available, reserved, sold, cancelled
- **OrderStatus**: pending, confirmed, cancelled, completed
- **TransactionStatus**: pending, success, failed, refunded

### Key Relationships
- User → Orders (One-to-Many)
- User → Cart Items (One-to-Many)
- Order → Order Items (One-to-Many)
- Ticket → Order Items (One-to-Many)
- Order → Transactions (One-to-Many)

## Development

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest
```

### Code Style
The project follows Python best practices:
- Type hints throughout
- Pydantic models for data validation
- SQLModel for database operations
- FastAPI for API framework

## Production Deployment

1. **Environment Variables**: Set production values in `.env`
2. **Database**: Configure production database (PostgreSQL recommended)
3. **Security**: Update SECRET_KEY and implement proper authentication
4. **CORS**: Configure CORS settings for your frontend
5. **Load Balancer**: Use nginx or similar for production deployment

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.
