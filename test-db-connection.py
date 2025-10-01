#!/usr/bin/env python3
"""
Test database connectivity for Ticket_and_Order_Service
"""
import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine, Session, select
from models import UserOrder

def test_connection():
    # Load environment variables
    load_dotenv()
    
    # Get database URL
    database_url = os.getenv("DATABASE_URL")
    print(f"Testing connection to: {database_url}")
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        # Test basic connection
        with Session(engine) as session:
            # Try a simple query
            result = session.execute(select(UserOrder).limit(1))
            orders = result.fetchall()
            print(f"✅ Database connection successful! Found {len(orders)} orders in database.")
            
        # Test table creation (this will create tables if they don't exist)
        print("Creating tables if they don't exist...")
        SQLModel.metadata.create_all(engine)
        print("✅ Tables created/verified successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    print("=== Testing PostgreSQL Connection ===")
    success = test_connection()
    if success:
        print("🎉 Database setup complete!")
    else:
        print("💥 Database setup failed!")