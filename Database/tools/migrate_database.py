#!/usr/bin/env python3
"""
Database Migration Script for Cart to Order Transition
This script will attempt to migrate data from an old schema to the new schema.
It's specifically designed to handle the transition from cart to order concepts.
"""

import os
import sys
import json
import uuid
import sqlite3
from datetime import datetime, timezone

# Add parent directory to path so we can import from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlmodel import SQLModel, create_engine, Session
from models import *
from database import DATABASE_URL

def backup_database():
    """Create a backup of the database before migration"""
    # Get DB path from DATABASE_URL
    db_path = DATABASE_URL.replace('sqlite:///', '')
    
    if os.path.exists(db_path):
        backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        backup_name = os.path.join(backup_dir, f"ticket_service_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        print(f"📦 Creating backup of database as {backup_name}...")
        
        # Use sqlite3 backup API or just copy the file
        try:
            import shutil
            shutil.copy2(db_path, backup_name)
            print(f"✅ Backup created successfully!")
            return True
        except Exception as e:
            print(f"❌ Error creating backup: {e}")
            return False
    else:
        print(f"❌ Database file not found at {db_path}, nothing to backup.")
        return False

def migrate_cart_to_order():
    """Migrate data from cart-based schema to order-based schema"""
    print("🔄 Starting cart to order migration...")
    
    # Connect to the database
    try:
        engine = create_engine(DATABASE_URL)
        
        # Get DB path from DATABASE_URL
        db_path = DATABASE_URL.replace('sqlite:///', '')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if we need to migrate UserOrder.id from INTEGER to TEXT for UUID
        print("🔍 Checking UserOrder.id type...")
        cursor.execute("PRAGMA table_info(userorder)")
        columns = cursor.fetchall()
        
        id_column = next((col for col in columns if col[1] == "id"), None)
        
        if id_column and "INT" in id_column[2].upper():
            print("⚠️  UserOrder.id is INTEGER, needs migration to TEXT for UUID support")
            
            # Get all existing orders
            cursor.execute("SELECT * FROM userorder")
            orders = cursor.fetchall()
            
            if orders:
                print(f"📝 Found {len(orders)} existing orders to migrate")
                
                # Get column names
                cursor.execute("PRAGMA table_info(userorder)")
                columns = [col[1] for col in cursor.fetchall()]
                
                # Backup order data
                orders_data = []
                for order in orders:
                    order_dict = {columns[i]: order[i] for i in range(len(columns))}
                    orders_data.append(order_dict)
                
                backup_dir = os.path.join(os.path.dirname(db_path), "backups")
                if not os.path.exists(backup_dir):
                    os.makedirs(backup_dir)
                
                backup_file = os.path.join(backup_dir, f"userorders_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                with open(backup_file, "w") as f:
                    json.dump(orders_data, f, indent=2, default=str)
                
                print(f"✅ Order data backed up to {backup_file}")
                
                # Drop and recreate the table
                print("🗑️  Dropping and recreating userorder table...")
                cursor.execute("DROP TABLE userorder")
                conn.commit()
                
                # Recreate the tables
                SQLModel.metadata.create_all(engine)
                
                # Reinsert the data with UUID strings
                print("🔄 Reinserting orders with UUID strings...")
                with Session(engine) as session:
                    for order_data in orders_data:
                        # Convert ID to UUID string if it was an integer
                        order_data["id"] = str(uuid.uuid4())
                        
                        # Create new order with proper ID type
                        new_order = UserOrder(
                            id=order_data["id"],
                            firebase_uid=order_data["firebase_uid"],
                            total_amount=order_data["total_amount"],
                            status=order_data.get("status", "PENDING"),
                            stripe_payment_id=order_data.get("stripe_payment_id"),
                            payment_intent_id=order_data.get("payment_intent_id"),
                            order_reference=order_data.get("order_reference"),
                            notes=order_data.get("notes"),
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        
                        session.add(new_order)
                    
                    session.commit()
                    
                print("✅ Orders migrated successfully with UUID string IDs!")
            else:
                print("ℹ️ No existing orders found, creating new schema...")
                
                # Drop and recreate the tables
                SQLModel.metadata.drop_all(engine)
                SQLModel.metadata.create_all(engine)
        else:
            print("✅ UserOrder.id is already using TEXT type, no migration needed")
            
        conn.close()
        print("✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        return False
        
    return True

if __name__ == "__main__":
    print("⚠️  WARNING: This will modify your database schema!")
    confirm = input("Are you sure you want to continue? (y/N): ")
    
    if confirm.lower() not in ['y', 'yes']:
        print("Operation cancelled.")
        sys.exit(0)
    
    # Create a backup first
    if backup_database():
        # Run the migration
        if migrate_cart_to_order():
            print("\n🎉 Database migration complete!")
        else:
            print("\n❌ Migration failed. Restore from backup if needed.")
    else:
        print("\n❌ Failed to create backup, migration aborted.")
        sys.exit(1)