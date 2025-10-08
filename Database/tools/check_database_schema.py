#!/usr/bin/env python3
"""
Database Schema Check Script
This script will display information about the current database schema and model definitions.
Use this to verify your models before resetting the database.
"""

import sys
import os
import sqlite3

# Add parent directory to path so we can import from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlmodel import SQLModel, create_engine, inspect
from models import *
from database import DATABASE_URL, get_session

def check_database_schema():
    """Check and display current database schema"""
    print("🔍 Checking database schema...")
    
    # Create SQLAlchemy engine
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    
    # Get all table names
    table_names = inspector.get_table_names()
    
    print(f"\n📊 Found {len(table_names)} tables in the database:")
    for table in table_names:
        print(f"  - {table}")
        
        # Get columns
        columns = inspector.get_columns(table)
        print(f"    Columns:")
        for col in columns:
            col_type = str(col['type']).split('(')[0]  # Simplified type name
            print(f"      - {col['name']} ({col_type}){' PRIMARY KEY' if col.get('primary_key') else ''}")
    
    # Show defined models
    print("\n📋 SQLModel defined models:")
    models = []
    
    # Get all subclasses of SQLModel that have a __tablename__ attribute
    for cls in SQLModel.__subclasses__():
        if hasattr(cls, '__tablename__'):
            models.append(cls)
            table_name = cls.__tablename__
            print(f"  - {cls.__name__} → {table_name}")
            
            # Show attributes 
            print(f"    Attributes:")
            for name, column in cls.model_fields.items():
                if name != '__pydantic_extra__':
                    field_type = str(column.annotation).split('[')[0]  # Simplified type
                    print(f"      - {name}: {field_type}")
    
    print(f"\n📝 Total SQLModel defined models: {len(models)}")
    
    # Check if all tables are represented by models
    missing_models = [t for t in table_names if t not in [m.__tablename__ for m in models if hasattr(m, '__tablename__')]]
    if missing_models:
        print(f"⚠️  Warning: Found {len(missing_models)} tables without corresponding models:")
        for table in missing_models:
            print(f"  - {table}")

def check_key_changes():
    """Check specific changes related to cart/order renaming"""
    print("\n🔑 Checking for cart/order key changes in UserOrder model...")
    
    try:
        # Check UserOrder model for ID type
        id_field = UserOrder.model_fields.get("id")
        if id_field:
            print(f"  ✅ UserOrder.id field type: {id_field.annotation}")
        else:
            print("  ❌ UserOrder model doesn't have an 'id' field")
            
        # Connect directly to SQLite to examine table structure
        # Get DB path from DATABASE_URL
        db_path = DATABASE_URL.replace('sqlite:///', '')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get info about UserOrder table
        cursor.execute("PRAGMA table_info(userorder)")
        columns = cursor.fetchall()
        
        id_column = next((col for col in columns if col[1] == "id"), None)
        if id_column:
            print(f"  ✅ Database userorder.id column type: {id_column[2]}")
            
            # Check if it's TEXT (string) or INTEGER
            if "TEXT" in id_column[2].upper():
                print("  ✅ UserOrder.id is using TEXT/string type (compatible with UUIDs)")
            elif "INT" in id_column[2].upper():
                print("  ⚠️  UserOrder.id is using INTEGER type (not compatible with UUID strings)")
        
        conn.close()
        
    except Exception as e:
        print(f"  ❌ Error checking UserOrder model: {e}")
    
if __name__ == "__main__":
    try:
        check_database_schema()
        check_key_changes()
        print("\n✅ Database schema check complete!")
    except Exception as e:
        print(f"❌ Error checking database schema: {e}")
        sys.exit(1)