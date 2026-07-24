"""
Database connection and session management for Kasaonu scraper
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine, event
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# Sanitize DATABASE_URL (strip quotes if they exist)
DATABASE_URL = DATABASE_URL.strip('"').strip("'")

# SQLAlchemy 1.4+ requires 'postgresql://' instead of 'postgres://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=20,
    max_overflow=30
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@event.listens_for(Session, "do_orm_execute")
def _block_campaign_delete(execute_state):
    if execute_state.is_delete and getattr(execute_state.bind_mapper, 'class_', None):
        class_name = execute_state.bind_mapper.class_.__name__
        if class_name == 'Campaign':
            allow_delete = os.getenv("ALLOW_CAMPAIGN_DELETE")
            if str(allow_delete) != "1":
                raise Exception("CRITICAL SAFETY LOCK: Deleting Campaigns via SQLAlchemy bulk operations is disabled to prevent accidental data loss. Use ALLOW_CAMPAIGN_DELETE=1 in your environment variables to override.")

# Base class for all models
Base = declarative_base()


def get_db():
    """
    Get database session (generator for context management)
    
    Usage:
        with get_db() as db:
            # Use db session
            pass
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """
    Get database session (direct)
    
    Usage:
        db = get_db_session()
        try:
            # Use db session
        finally:
            db.close()
    """
    return SessionLocal()
