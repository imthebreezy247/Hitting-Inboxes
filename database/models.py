# database/models.py
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import os

class DatabaseManager:
    def __init__(self, db_path: str = "email_system.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with all required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Subscribers table
        cursor.execute('''
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
                preferences TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Email campaigns table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                html_content TEXT,
                text_content TEXT,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Email sends table (individual email tracking)
        cursor.execute('''
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
        
        # ESP performance tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS esp_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                date DATE NOT NULL,
                sent_count INTEGER DEFAULT 0,
                delivered_count INTEGER DEFAULT 0,
                bounced_count INTEGER DEFAULT 0,
                complained_count INTEGER DEFAULT 0,
                delivery_rate REAL DEFAULT 0.0,
                bounce_rate REAL DEFAULT 0.0,
                complaint_rate REAL DEFAULT 0.0,
                reputation_score REAL DEFAULT 100.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, date)
            )
        ''')
        
        # Bounce tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bounces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                bounce_type TEXT NOT NULL,
                bounce_reason TEXT,
                esp_provider TEXT,
                bounce_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                campaign_id INTEGER,
                is_permanent BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
            )
        ''')
        
        # Complaints tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                complaint_type TEXT,
                esp_provider TEXT,
                complaint_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                campaign_id INTEGER,
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
            )
        ''')
        
        # System settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscribers_email ON subscribers(email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscribers_status ON subscribers(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_sends_campaign ON email_sends(campaign_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_sends_subscriber ON email_sends(subscriber_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_sends_esp ON email_sends(esp_provider)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bounces_email ON bounces(email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_complaints_email ON complaints(email)')
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def execute_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute query and return results as list of dictionaries"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    
    def execute_update(self, query: str, params: tuple = ()) -> int:
        """Execute update/insert query and return affected rows"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        affected_rows = cursor.rowcount
        conn.commit()
        conn.close()
        return affected_rows
    
    def migrate_from_json(self, json_file: str = "subscribers.json"):
        """Migrate existing JSON subscriber data to database"""
        if not os.path.exists(json_file):
            return
        
        try:
            with open(json_file, 'r') as f:
                subscribers = json.load(f)
            
            for sub in subscribers:
                self.execute_update('''
                    INSERT OR REPLACE INTO subscribers 
                    (email, name, company, status, subscribed_date, bounce_count, last_engaged)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    sub.get('email'),
                    sub.get('name'),
                    sub.get('company'),
                    sub.get('status', 'active'),
                    sub.get('subscribed_date'),
                    sub.get('bounce_count', 0),
                    sub.get('last_engaged')
                ))
            
            print(f"Migrated {len(subscribers)} subscribers from JSON to database")
            
        except Exception as e:
            print(f"Error migrating from JSON: {e}")

# Initialize database instance
db = DatabaseManager()
