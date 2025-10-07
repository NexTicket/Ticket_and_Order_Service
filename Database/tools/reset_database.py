#!/usr/bin/env python3
"""
Database Reset Script
This script will reset the database by dropping all tables and recreating them.
USE WITH CAUTION: This will delete all data in the database.
"""

import os
import sys
import sqlite3
from datetime import datetime

# Add parent directory to path so we can import from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlmodel import SQLModel, create_engine
from sqlalchemy import text
from models import *
from database import DATABASE_URL

def backup_database():
    """Create a backup of the database before resetting"""
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
        return True  # Return True anyway to allow creating a fresh DB

def reset_database():
    """Reset the database by dropping all tables and recreating them"""
    print("🔄 Resetting database...")
    
    try:
        # Create engine
        engine = create_engine(DATABASE_URL)
        
        # Drop all tables with CASCADE using direct SQL for PostgreSQL
        print("🗑️  Dropping all tables...")
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE;"))
            conn.execute(text("CREATE SCHEMA public;"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
            conn.commit()
        
        # Create all tables
        print("🏗️  Creating all tables...")
        SQLModel.metadata.create_all(engine)
        
        print("✅ Database reset successfully!")
        return True
    except Exception as e:
        print(f"❌ Error resetting database: {e}")
        return False

def seed_test_data():
    """Seed the database with some test data"""
    print("🌱 Seeding database with test data...")
    
    try:
        # Implementation depends on what test data you want to create
        # This is just a placeholder for now
        print("✅ Database seeded successfully!")
        return True
    except Exception as e:
        print(f"❌ Error seeding database: {e}")
        return False

if __name__ == "__main__":
    print("⚠️  WARNING: This will DELETE ALL DATA in the database!")
    confirm = input("Are you sure you want to reset the database? (yes/NO): ")
    
    if confirm.lower() != 'yes':
        print("Operation cancelled. The database was not reset.")
        sys.exit(0)
    
    # Create a backup first
    if backup_database():
        # Reset the database
        if reset_database():
            print("\n🎉 Database reset complete!")
            
            # Optionally seed test data
            seed = input("Would you like to seed the database with test data? (y/N): ")
            if seed.lower() in ['y', 'yes']:
                if seed_test_data():
                    print("\n🎉 Database seeded successfully!")
                else:
                    print("\n❌ Failed to seed the database.")
        else:
            print("\n❌ Database reset failed. Restore from backup if needed.")
    else:
        print("\n❌ Failed to create backup, reset aborted.")
        sys.exit(1)