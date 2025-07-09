# src/database/models.py
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, JSON, ForeignKey, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class Subscriber(Base):
    __tablename__ = 'subscribers'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255))
    company = Column(String(255))
    status = Column(String(50), default='active', index=True)  # active, unsubscribed, bounced, complained
    
    # Engagement metrics
    engagement_score = Column(Float, default=0.5, index=True)
    last_open = Column(DateTime, index=True)
    last_click = Column(DateTime, index=True)
    total_sent = Column(Integer, default=0)
    total_opens = Column(Integer, default=0)
    total_clicks = Column(Integer, default=0)
    
    # Quality metrics
    bounce_count = Column(Integer, default=0)
    complaint_count = Column(Integer, default=0)
    
    # Segmentation
    segment = Column(String(100), default='general', index=True)
    tags = Column(JSON)
    time_zone = Column(String(50), default='US/Eastern')
    
    # Metadata
    custom_fields = Column(JSON)
    source = Column(String(100))
    subscribed_date = Column(DateTime, default=datetime.utcnow, index=True)
    unsubscribed_date = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    engagements = relationship("Engagement", back_populates="subscriber")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_subscriber_engagement', 'engagement_score', 'status'),
        Index('idx_subscriber_activity', 'last_open', 'last_click'),
    )

class Campaign(Base):
    __tablename__ = 'campaigns'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    from_name = Column(String(255))
    from_email = Column(String(255))
    
    # Content
    html_content = Column(Text)
    text_content = Column(Text)
    template_id = Column(Integer)
    
    # Scheduling and targeting
    scheduled_time = Column(DateTime, index=True)
    sent_time = Column(DateTime)
    time_zone = Column(String(50), default='US/Eastern')
    segment_rules = Column(JSON)
    
    # Campaign settings
    send_time_optimization = Column(Boolean, default=True)
    provider_preference = Column(String(50))
    warming_campaign = Column(Boolean, default=False)
    
    # Metrics
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)
    open_count = Column(Integer, default=0)
    click_count = Column(Integer, default=0)
    bounce_count = Column(Integer, default=0)
    complaint_count = Column(Integer, default=0)
    unsubscribe_count = Column(Integer, default=0)
    
    # Performance metrics
    delivery_rate = Column(Float, default=0.0)
    open_rate = Column(Float, default=0.0)
    click_rate = Column(Float, default=0.0)
    bounce_rate = Column(Float, default=0.0)
    
    # Status and metadata
    status = Column(String(50), default='draft', index=True)  # draft, scheduled, sending, sent, paused, failed
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    engagements = relationship("Engagement", back_populates="campaign")

class Engagement(Base):
    __tablename__ = 'engagements'
    
    id = Column(Integer, primary_key=True)
    subscriber_id = Column(Integer, ForeignKey('subscribers.id'), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'), nullable=False, index=True)
    
    # Delivery information
    provider_used = Column(String(50), index=True)
    ip_address_used = Column(String(45))
    message_id = Column(String(255))
    
    # Engagement tracking with precise timestamps
    sent_at = Column(DateTime, index=True)
    delivered_at = Column(DateTime)
    opened_at = Column(DateTime)
    clicked_at = Column(DateTime)
    bounced_at = Column(DateTime)
    complained_at = Column(DateTime)
    unsubscribed_at = Column(DateTime)
    
    # Technical details
    bounce_type = Column(String(50))  # hard, soft, blocked, suppressed
    bounce_reason = Column(String(500))
    complaint_type = Column(String(50))  # spam, not-spam, virus
    
    # Tracking data
    user_agent = Column(String(500))
    ip_address = Column(String(45))
    location_data = Column(JSON)
    device_info = Column(JSON)
    
    # Performance flags
    is_delivered = Column(Boolean, default=False, index=True)
    is_opened = Column(Boolean, default=False, index=True)
    is_clicked = Column(Boolean, default=False, index=True)
    is_bounced = Column(Boolean, default=False, index=True)
    is_complained = Column(Boolean, default=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    subscriber = relationship("Subscriber", back_populates="engagements")
    campaign = relationship("Campaign", back_populates="engagements")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_engagement_tracking', 'campaign_id', 'sent_at'),
        Index('idx_engagement_events', 'opened_at', 'clicked_at'),
        Index('idx_engagement_provider', 'provider_used', 'sent_at'),
    )

class ProviderPerformance(Base):
    __tablename__ = 'provider_performance'
    
    id = Column(Integer, primary_key=True)
    provider_name = Column(String(50), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    
    # Volume metrics
    emails_sent = Column(Integer, default=0)
    emails_delivered = Column(Integer, default=0)
    emails_bounced = Column(Integer, default=0)
    emails_complained = Column(Integer, default=0)
    
    # Rate metrics
    delivery_rate = Column(Float, default=0.0)
    bounce_rate = Column(Float, default=0.0)
    complaint_rate = Column(Float, default=0.0)
    
    # Reputation metrics
    reputation_score = Column(Float, default=1.0)
    ip_reputation = Column(Float, default=1.0)
    domain_reputation = Column(Float, default=1.0)
    
    # Performance metrics
    average_delivery_time = Column(Float, default=0.0)  # seconds
    success_rate = Column(Float, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint
    __table_args__ = (
        Index('idx_provider_date', 'provider_name', 'date', unique=True),
    )

class WarmingProgress(Base):
    __tablename__ = 'warming_progress'
    
    id = Column(Integer, primary_key=True)
    provider_name = Column(String(50), nullable=False, index=True)
    warming_day = Column(Integer, nullable=False)
    date = Column(DateTime, nullable=False, index=True)
    
    # Planned vs actual
    planned_volume = Column(Integer, default=0)
    actual_volume = Column(Integer, default=0)
    planned_segment = Column(String(100))
    
    # Performance metrics
    delivery_rate = Column(Float, default=0.0)
    open_rate = Column(Float, default=0.0)
    click_rate = Column(Float, default=0.0)
    bounce_rate = Column(Float, default=0.0)
    complaint_rate = Column(Float, default=0.0)
    
    # Status
    status = Column(String(50), default='active')  # active, paused, completed, failed
    notes = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class EmailTemplate(Base):
    __tablename__ = 'email_templates'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Template content
    html_content = Column(Text)
    text_content = Column(Text)
    subject_template = Column(String(255))
    
    # Template metadata
    category = Column(String(100))
    tags = Column(JSON)
    variables = Column(JSON)  # Available template variables
    
    # Performance tracking
    usage_count = Column(Integer, default=0)
    average_open_rate = Column(Float, default=0.0)
    average_click_rate = Column(Float, default=0.0)
    
    # Status
    is_active = Column(Boolean, default=True)
    created_by = Column(String(255))
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Database configuration
def get_database_url():
    """Get database URL from environment or use SQLite as fallback"""
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        return db_url
    
    # Fallback to SQLite for development
    return 'sqlite:///email_system.db'

# Create engine and session
engine = create_engine(get_database_url(), echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
