# src/database/async_models.py
import asyncio
import aiosqlite
import logging
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
import json
import os
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AsyncDatabaseManager:
    """
    Async Database Manager with connection pooling
    Handles all database operations asynchronously
    """
    
    def __init__(self, db_path: str = "email_system.db", pool_size: int = 10):
        self.db_path = db_path
        self.pool_size = pool_size
        self._connection_pool = []
        self._pool_lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self):
        """Initialize database and connection pool"""
        if self._initialized:
            return
        
        # Create database file if it doesn't exist
        if not os.path.exists(self.db_path):
            await self._create_database_schema()
        
        # Initialize connection pool
        async with self._pool_lock:
            for _ in range(self.pool_size):
                conn = await aiosqlite.connect(self.db_path)
                conn.row_factory = aiosqlite.Row
                self._connection_pool.append(conn)
        
        self._initialized = True
        logger.info(f"Initialized async database with {self.pool_size} connections")
    
    async def _create_database_schema(self):
        """Create database schema"""
        async with aiosqlite.connect(self.db_path) as conn:
            # Subscribers table
            await conn.execute('''
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
            await conn.execute('''
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
            await conn.execute('''
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
            
            # Engagement events table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS engagement_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_send_id INTEGER,
                    event_type TEXT NOT NULL,
                    event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_agent TEXT,
                    ip_address TEXT,
                    clicked_url TEXT,
                    bounce_type TEXT,
                    bounce_reason TEXT,
                    metadata TEXT,
                    FOREIGN KEY (email_send_id) REFERENCES email_sends (id)
                )
            ''')

            # Delivery events table for webhook processing
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS delivery_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    email TEXT NOT NULL,
                    campaign_id INTEGER,
                    esp_provider TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_message_id (message_id),
                    INDEX idx_email (email),
                    INDEX idx_event_type (event_type),
                    INDEX idx_timestamp (timestamp),
                    FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
                )
            ''')
            
            # ESP provider stats table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS esp_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_name TEXT NOT NULL,
                    date DATE NOT NULL,
                    emails_sent INTEGER DEFAULT 0,
                    emails_delivered INTEGER DEFAULT 0,
                    emails_bounced INTEGER DEFAULT 0,
                    emails_complained INTEGER DEFAULT 0,
                    reputation_score REAL DEFAULT 100.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider_name, date)
                )
            ''')
            
            # Create indexes for better performance
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_subscribers_email ON subscribers(email)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_subscribers_status ON subscribers(status)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_email_sends_campaign ON email_sends(campaign_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_email_sends_subscriber ON email_sends(subscriber_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_email_sends_esp ON email_sends(esp_provider)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_engagement_events_send ON engagement_events(email_send_id)')
            
            await conn.commit()
            logger.info("Database schema created successfully")
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get connection from pool"""
        if not self._initialized:
            await self.initialize()
        
        connection = None
        try:
            async with self._pool_lock:
                if self._connection_pool:
                    connection = self._connection_pool.pop()
                else:
                    # Pool exhausted, create temporary connection
                    connection = await aiosqlite.connect(self.db_path)
                    connection.row_factory = aiosqlite.Row
                    logger.warning("Connection pool exhausted, created temporary connection")
            
            yield connection
            
        finally:
            if connection:
                async with self._pool_lock:
                    if len(self._connection_pool) < self.pool_size:
                        self._connection_pool.append(connection)
                    else:
                        await connection.close()
    
    async def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute SELECT query and return results"""
        async with self.get_connection() as conn:
            try:
                cursor = await conn.execute(query, params)
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Query execution failed: {query} - {str(e)}")
                raise
    
    async def execute_update(self, query: str, params: tuple = ()) -> int:
        """Execute INSERT/UPDATE/DELETE query and return affected rows"""
        async with self.get_connection() as conn:
            try:
                cursor = await conn.execute(query, params)
                await conn.commit()
                return cursor.rowcount
            except Exception as e:
                logger.error(f"Update execution failed: {query} - {str(e)}")
                await conn.rollback()
                raise
    
    async def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute query with multiple parameter sets"""
        async with self.get_connection() as conn:
            try:
                cursor = await conn.executemany(query, params_list)
                await conn.commit()
                return cursor.rowcount
            except Exception as e:
                logger.error(f"Batch execution failed: {query} - {str(e)}")
                await conn.rollback()
                raise
    
    async def get_subscriber_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get subscriber by email address"""
        query = "SELECT * FROM subscribers WHERE email = ? AND status = 'active'"
        results = await self.execute_query(query, (email,))
        return results[0] if results else None
    
    async def get_campaign_subscribers(self, campaign_id: int, segment_rules: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Get subscribers for a campaign"""
        base_query = "SELECT * FROM subscribers WHERE status = 'active'"
        params = []
        
        # Apply segment rules if provided
        if segment_rules:
            if 'segment' in segment_rules:
                base_query += " AND segment = ?"
                params.append(segment_rules['segment'])
            
            if 'min_engagement_score' in segment_rules:
                base_query += " AND engagement_score >= ?"
                params.append(segment_rules['min_engagement_score'])
        
        base_query += " ORDER BY engagement_score DESC"
        
        return await self.execute_query(base_query, tuple(params))
    
    async def record_email_send(self, campaign_id: int, subscriber_id: int, email: str, 
                               esp_provider: str, message_id: str, status: str = 'sent') -> int:
        """Record email send in database"""
        query = '''
            INSERT INTO email_sends 
            (campaign_id, subscriber_id, email, esp_provider, message_id, status, sent_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        '''
        params = (campaign_id, subscriber_id, email, esp_provider, message_id, status, datetime.utcnow())
        
        await self.execute_update(query, params)
        
        # Get the inserted ID
        async with self.get_connection() as conn:
            cursor = await conn.execute("SELECT last_insert_rowid()")
            result = await cursor.fetchone()
            return result[0] if result else 0
    
    async def update_campaign_stats(self, campaign_id: int, stats: Dict[str, int]):
        """Update campaign statistics"""
        query = '''
            UPDATE campaigns 
            SET sent_count = ?, delivered_count = ?, opened_count = ?, 
                clicked_count = ?, bounced_count = ?, complained_count = ?,
                updated_at = ?
            WHERE id = ?
        '''
        params = (
            stats.get('sent_count', 0),
            stats.get('delivered_count', 0),
            stats.get('opened_count', 0),
            stats.get('clicked_count', 0),
            stats.get('bounced_count', 0),
            stats.get('complained_count', 0),
            datetime.utcnow(),
            campaign_id
        )
        
        return await self.execute_update(query, params)
    
    async def get_engagement_stats(self, campaign_id: Optional[int] = None, 
                                  days: int = 30) -> Dict[str, Any]:
        """Get engagement statistics"""
        base_query = '''
            SELECT 
                COUNT(*) as total_sent,
                SUM(CASE WHEN delivered_time IS NOT NULL THEN 1 ELSE 0 END) as delivered,
                SUM(CASE WHEN opened_time IS NOT NULL THEN 1 ELSE 0 END) as opened,
                SUM(CASE WHEN clicked_time IS NOT NULL THEN 1 ELSE 0 END) as clicked,
                SUM(CASE WHEN bounced_time IS NOT NULL THEN 1 ELSE 0 END) as bounced,
                SUM(CASE WHEN complained_time IS NOT NULL THEN 1 ELSE 0 END) as complained
            FROM email_sends 
            WHERE sent_time >= datetime('now', '-{} days')
        '''.format(days)
        
        params = []
        if campaign_id:
            base_query += " AND campaign_id = ?"
            params.append(campaign_id)
        
        results = await self.execute_query(base_query, tuple(params))
        
        if results:
            stats = results[0]
            total = stats['total_sent'] or 1  # Avoid division by zero
            
            return {
                'total_sent': stats['total_sent'],
                'delivered': stats['delivered'],
                'opened': stats['opened'],
                'clicked': stats['clicked'],
                'bounced': stats['bounced'],
                'complained': stats['complained'],
                'delivery_rate': (stats['delivered'] / total) * 100,
                'open_rate': (stats['opened'] / total) * 100,
                'click_rate': (stats['clicked'] / total) * 100,
                'bounce_rate': (stats['bounced'] / total) * 100,
                'complaint_rate': (stats['complained'] / total) * 100
            }
        
        return {
            'total_sent': 0, 'delivered': 0, 'opened': 0, 'clicked': 0,
            'bounced': 0, 'complained': 0, 'delivery_rate': 0,
            'open_rate': 0, 'click_rate': 0, 'bounce_rate': 0, 'complaint_rate': 0
        }
    
    async def close_all_connections(self):
        """Close all connections in pool"""
        async with self._pool_lock:
            for conn in self._connection_pool:
                await conn.close()
            self._connection_pool.clear()
        
        logger.info("All database connections closed")

# Global database instance
async_db = AsyncDatabaseManager()

async def get_async_db() -> AsyncDatabaseManager:
    """Get async database instance"""
    if not async_db._initialized:
        await async_db.initialize()
    return async_db
