# src/database/models.py
import sqlite3
import logging
from typing import Generator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = "email_system.db"

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Get database connection (legacy sync version)"""
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def create_tables():
    """Create database tables (legacy sync version)"""
    conn = sqlite3.connect(DATABASE_URL)
    
    try:
        # Subscribers table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                company TEXT,
                status TEXT DEFAULT 'active',
                subscribed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                unsubscribed_date TIMESTAMP,
                bounce_count INTEGER DEFAULT 0,
                complaint_count INTEGER DEFAULT 0,
                last_engaged TIMESTAMP,
                engagement_score REAL DEFAULT 100.0,
                segment TEXT DEFAULT 'general',
                source TEXT,
                custom_fields TEXT,
                tags TEXT,
                time_zone TEXT DEFAULT 'US/Eastern',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Campaigns table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                html_content TEXT,
                text_content TEXT,
                from_name TEXT,
                from_email TEXT,
                status TEXT DEFAULT 'draft',
                scheduled_time TIMESTAMP,
                sent_time TIMESTAMP,
                total_recipients INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                delivered_count INTEGER DEFAULT 0,
                opened_count INTEGER DEFAULT 0,
                clicked_count INTEGER DEFAULT 0,
                bounced_count INTEGER DEFAULT 0,
                complained_count INTEGER DEFAULT 0,
                unsubscribed_count INTEGER DEFAULT 0,
                esp_used TEXT,
                segment_rules TEXT,
                send_time_optimization BOOLEAN DEFAULT TRUE,
                warming_campaign BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Email sends table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS email_sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER,
                subscriber_id INTEGER,
                email TEXT NOT NULL,
                esp_provider TEXT NOT NULL,
                status TEXT DEFAULT 'sent',
                sent_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delivered_time TIMESTAMP,
                opened_time TIMESTAMP,
                clicked_time TIMESTAMP,
                bounced_time TIMESTAMP,
                bounce_reason TEXT,
                complained_time TIMESTAMP,
                unsubscribed_time TIMESTAMP,
                message_id TEXT,
                tracking_data TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id),
                FOREIGN KEY (subscriber_id) REFERENCES subscribers (id)
            )
        ''')
        
        conn.commit()
        logger.info("Database tables created successfully")
        
    except Exception as e:
        logger.error(f"Error creating tables: {str(e)}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    create_tables()
