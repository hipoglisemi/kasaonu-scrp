import os
"""
SQLAlchemy models matching Prisma schema
Complete implementation of all tables and columns
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Numeric, Text,
    ForeignKey, Index, ARRAY, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from decimal import Decimal
import uuid

# Try relative import first (for module usage), fall back to absolute (for script usage)
try:
    from .database import Base
except ImportError:
    from database import Base


# ============================================
# CORE ENTITIES
# ============================================

class Bank(Base):
    """Bank entity - stores credit card issuing banks"""
    __tablename__ = "banks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    logo_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Alias support for banks (e.g. Garanti, Garanti BBVA)
    aliases = Column(ARRAY(String), default=list, nullable=False)

    # Relationships
    cards = relationship("Card", back_populates="bank", cascade="all, delete-orphan")


class Card(Base):
    """Card entity - stores credit card products"""
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_id = Column(Integer, ForeignKey("banks.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    card_type = Column(String, nullable=True)
    annual_fee = Column(Numeric(10, 2), nullable=True)
    application_url = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)     # For small logos
    credit_logo_url = Column(String, nullable=True) # For card visual
    image_url = Column(String, nullable=True)       # For card image
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    bank = relationship("Bank", back_populates="cards")
    campaigns = relationship("Campaign", back_populates="card", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_cards_bank_id", "bank_id"),
    )


class Sector(Base):
    """Sector entity - categorizes brands and campaigns (Market, Yakıt, etc.)"""
    __tablename__ = "sectors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    image_url = Column(String, nullable=True)
    icon_name = Column(String, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    # brands = relationship("Brand", back_populates="sector") # REMOVED: Brand no longer has sector_id
    campaigns = relationship("Campaign", back_populates="sector")


class Brand(Base):
    """Brand entity - stores merchants/brands (Migros, Zara, etc.)"""
    __tablename__ = "brands"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    # sector_id = Column(Integer, ForeignKey("sectors.id"), nullable=False) # REMOVED
    aliases = Column(ARRAY(String), default=list, nullable=False)
    logo_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    # sector = relationship("Sector", back_populates="brands") # REMOVED
    campaigns = relationship("CampaignBrand", back_populates="brand", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        # Index("ix_brands_sector_id", "sector_id"), # REMOVED
    )


class Campaign(Base):
    """Campaign entity - stores credit card campaigns with all details"""
    __tablename__ = "test_campaigns" if os.environ.get("TEST_MODE") == "1" else "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    card_id = Column(Integer, ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    sector_id = Column(Integer, ForeignKey("sectors.id"), nullable=True)
    
    # SEO slug
    slug = Column(String, unique=True, nullable=False)
    
    # Core campaign data
    title = Column(String, nullable=False)
    reward_text = Column(String, nullable=True)
    reward_value = Column(Numeric(10, 2), nullable=True)
    reward_type = Column(String, nullable=True)  # cashback, points, discount, installment
    
    # Updated fields matching Prisma Schema
    description = Column(Text, nullable=True)   # Was details_text
    conditions = Column(Text, nullable=True)    # Was conditions_text
    
    image_url = Column(String, nullable=True)
    
    # Custom Fields from Prisma
    ai_marketing_text = Column(String, nullable=True)
    participation = Column(String, nullable=True)
    eligible_cards = Column(String, nullable=True)
    category = Column(String, nullable=True)
    badge_color = Column(String, nullable=True)
    card_logo_url = Column(String, nullable=True)
    clean_text = Column(Text, nullable=True)

    # Quality Control
    quality_score = Column(Integer, nullable=True)
    auto_corrected = Column(Boolean, default=False, nullable=False)

    # Dates
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    
    # Status and tracking
    is_active = Column(Boolean, default=True, nullable=False)
    tracking_url = Column(String, nullable=True)
    affiliate_network = Column(String, nullable=True)
    view_count = Column(Integer, default=0, nullable=False)
    click_count = Column(Integer, default=0, nullable=False)
    
    # AI embedding (vector for semantic search)
    # Note: Using String for now, Prisma uses vector(1536)
    # embedding = Column(String, nullable=True)  # Skip for now
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    card = relationship("Card", back_populates="campaigns")
    sector = relationship("Sector", back_populates="campaigns")
    brands = relationship("CampaignBrand", back_populates="campaign", cascade="all, delete-orphan")
    search_logs = relationship("SearchLog", back_populates="clicked_campaign")

    # Indexes
    __table_args__ = (
        Index("ix_campaigns_card_id", "card_id"),
        Index("ix_campaigns_sector_id", "sector_id"),
        Index("ix_campaigns_dates", "start_date", "end_date"),
    )


class CampaignBrand(Base):
    """Many-to-many relationship between campaigns and brands"""
    __tablename__ = "test_campaign_brands" if os.environ.get("TEST_MODE") == "1" else "campaign_brands"

    campaign_id = Column(Integer, ForeignKey("test_campaigns.id" if os.environ.get("TEST_MODE") == "1" else "campaigns.id", ondelete="CASCADE"), primary_key=True)
    brand_id = Column(UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), primary_key=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="brands")
    brand = relationship("Brand", back_populates="campaigns")

    # Indexes
    __table_args__ = (
        Index("ix_campaign_brands_brand_id", "brand_id"),
    )


# ============================================
# ANALYTICS (Optional - for future use)
# ============================================

class UserSession(Base):
    """User session tracking"""
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint = Column(String, unique=True, nullable=False)
    saved_cards = Column(ARRAY(Integer), default=list, nullable=False)
    last_search_query = Column(String, nullable=True)
    last_seen_at = Column(DateTime, default=func.now(), nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    search_logs = relationship("SearchLog", back_populates="session")


class SearchLog(Base):
    """Search query logging"""
    __tablename__ = "search_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("user_sessions.id", ondelete="SET NULL"), nullable=True)
    query = Column(String, nullable=False)
    result_count = Column(Integer, nullable=True)
    clicked_campaign_id = Column(Integer, ForeignKey("test_campaigns.id" if os.environ.get("TEST_MODE") == "1" else "campaigns.id", ondelete="SET NULL"), nullable=True)
    searched_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    session = relationship("UserSession", back_populates="search_logs")
    clicked_campaign = relationship("Campaign", back_populates="search_logs")

    # Indexes
    __table_args__ = (
        Index("ix_search_logs_query", "query"),
        Index("ix_search_logs_searched_at", "searched_at"),
    )


class MissingSearch(Base):
    """Track searches with no results"""
    __tablename__ = "missing_searches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String, unique=True, nullable=False)
    search_count = Column(Integer, default=1, nullable=False)
    last_searched_at = Column(DateTime, default=func.now(), nullable=False)
    suggested_sector_id = Column(Integer, nullable=True)
    is_resolved = Column(Boolean, default=False, nullable=False)

    # Indexes
    __table_args__ = (
        Index("ix_missing_searches_query", "query"),
    )

class CampaignBlocklist(Base):
    """Blocklist for campaigns that should not be scraped or displayed"""
    __tablename__ = "campaign_blocklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    campaign_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Indexes
    __table_args__ = (
        Index("ix_campaign_blocklist_url", "url"),
    )

class ScraperLog(Base):
    """Execution logs for scrapers"""
    __tablename__ = "scraper_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scraper_name = Column(String, nullable=False)
    status = Column(String, nullable=False) # SUCCESS, FAILED, PARTIAL
    total_found = Column(Integer, default=0, nullable=False)
    total_saved = Column(Integer, default=0, nullable=False)
    total_skipped = Column(Integer, default=0, nullable=False)
    total_failed = Column(Integer, default=0, nullable=False)
    error_log = Column(JSON, nullable=True) # Needs sqlalchemy.JSON
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Indexes
    __table_args__ = (
        Index("ix_scraper_logs_name", "scraper_name"),
        Index("ix_scraper_logs_status", "status"),
        Index("ix_scraper_logs_created_at", "created_at"),
    )


