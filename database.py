from dotenv import load_dotenv
import os
from sqlmodel import SQLModel, create_engine, Session

load_dotenv()

# Use PostgreSQL database (shared with Event_and_Venue_Service)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# PostgreSQL doesn't need connect_args like SQLite
engine = create_engine(DATABASE_URL, echo=True)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
