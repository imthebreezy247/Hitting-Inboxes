# src/database/engagement_tracker.py
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EngagementTracker:
    """
    Tracks email engagement events (legacy sync version)
    For async operations, use AsyncDatabaseManager directly
    """
    
    def __init__(self, db_session):
        self.db = db_session
    
    def record_email_send(self, campaign_id: int, subscriber_id: int, email: str,
                         esp_provider: str, message_id: str, status: str = 'sent') -> bool:
        """Record email send event"""
        try:
            query = '''
                INSERT INTO email_sends 
                (campaign_id, subscriber_id, email, esp_provider, message_id, status, sent_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            '''
            params = (campaign_id, subscriber_id, email, esp_provider, message_id, status, datetime.utcnow())
            
            cursor = self.db.execute(query, params)
            self.db.commit()
            
            logger.debug(f"Recorded email send: {email} via {esp_provider}")
            return True
            
        except Exception as e:
            logger.error(f"Error recording email send: {str(e)}")
            self.db.rollback()
            return False
    
    def record_delivery(self, message_id: str, delivered_time: Optional[datetime] = None) -> bool:
        """Record email delivery event"""
        try:
            if not delivered_time:
                delivered_time = datetime.utcnow()
            
            query = '''
                UPDATE email_sends 
                SET status = 'delivered', delivered_time = ?
                WHERE message_id = ?
            '''
            params = (delivered_time, message_id)
            
            cursor = self.db.execute(query, params)
            self.db.commit()
            
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error recording delivery for {message_id}: {str(e)}")
            self.db.rollback()
            return False
    
    def record_open(self, message_id: str, user_agent: Optional[str] = None,
                   ip_address: Optional[str] = None, opened_time: Optional[datetime] = None) -> bool:
        """Record email open event"""
        try:
            if not opened_time:
                opened_time = datetime.utcnow()
            
            # Update email_sends table
            query = '''
                UPDATE email_sends 
                SET opened_time = ?
                WHERE message_id = ? AND opened_time IS NULL
            '''
            cursor = self.db.execute(query, (opened_time, message_id))
            
            # Record engagement event
            if cursor.rowcount > 0:
                self._record_engagement_event(message_id, 'open', opened_time, user_agent, ip_address)
            
            self.db.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error recording open for {message_id}: {str(e)}")
            self.db.rollback()
            return False
    
    def record_click(self, message_id: str, clicked_url: str, user_agent: Optional[str] = None,
                    ip_address: Optional[str] = None, clicked_time: Optional[datetime] = None) -> bool:
        """Record email click event"""
        try:
            if not clicked_time:
                clicked_time = datetime.utcnow()
            
            # Update email_sends table (only first click)
            query = '''
                UPDATE email_sends 
                SET clicked_time = ?
                WHERE message_id = ? AND clicked_time IS NULL
            '''
            cursor = self.db.execute(query, (clicked_time, message_id))
            
            # Always record click event (can have multiple clicks)
            self._record_engagement_event(message_id, 'click', clicked_time, user_agent, ip_address, clicked_url)
            
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error recording click for {message_id}: {str(e)}")
            self.db.rollback()
            return False
    
    def record_bounce(self, message_id: str, bounce_type: str, bounce_reason: str,
                     bounced_time: Optional[datetime] = None) -> bool:
        """Record email bounce event"""
        try:
            if not bounced_time:
                bounced_time = datetime.utcnow()
            
            # Update email_sends table
            query = '''
                UPDATE email_sends 
                SET status = 'bounced', bounced_time = ?, bounce_reason = ?
                WHERE message_id = ?
            '''
            cursor = self.db.execute(query, (bounced_time, bounce_reason, message_id))
            
            # Record engagement event
            if cursor.rowcount > 0:
                metadata = {'bounce_type': bounce_type, 'bounce_reason': bounce_reason}
                self._record_engagement_event(message_id, 'bounce', bounced_time, metadata=metadata)
            
            self.db.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error recording bounce for {message_id}: {str(e)}")
            self.db.rollback()
            return False
    
    def record_complaint(self, message_id: str, complained_time: Optional[datetime] = None) -> bool:
        """Record spam complaint event"""
        try:
            if not complained_time:
                complained_time = datetime.utcnow()
            
            # Update email_sends table
            query = '''
                UPDATE email_sends 
                SET complained_time = ?
                WHERE message_id = ?
            '''
            cursor = self.db.execute(query, (complained_time, message_id))
            
            # Record engagement event
            if cursor.rowcount > 0:
                self._record_engagement_event(message_id, 'complaint', complained_time)
            
            self.db.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error recording complaint for {message_id}: {str(e)}")
            self.db.rollback()
            return False
    
    def record_unsubscribe(self, message_id: str, unsubscribed_time: Optional[datetime] = None) -> bool:
        """Record unsubscribe event"""
        try:
            if not unsubscribed_time:
                unsubscribed_time = datetime.utcnow()
            
            # Update email_sends table
            query = '''
                UPDATE email_sends 
                SET unsubscribed_time = ?
                WHERE message_id = ?
            '''
            cursor = self.db.execute(query, (unsubscribed_time, message_id))
            
            # Record engagement event
            if cursor.rowcount > 0:
                self._record_engagement_event(message_id, 'unsubscribe', unsubscribed_time)
            
            self.db.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error recording unsubscribe for {message_id}: {str(e)}")
            self.db.rollback()
            return False
    
    def _record_engagement_event(self, message_id: str, event_type: str, event_time: datetime,
                                user_agent: Optional[str] = None, ip_address: Optional[str] = None,
                                clicked_url: Optional[str] = None, metadata: Optional[Dict] = None):
        """Record detailed engagement event"""
        try:
            # Get email_send_id
            query = "SELECT id FROM email_sends WHERE message_id = ?"
            cursor = self.db.execute(query, (message_id,))
            row = cursor.fetchone()
            
            if not row:
                logger.warning(f"No email send found for message_id: {message_id}")
                return
            
            email_send_id = row['id']
            
            # Insert engagement event
            query = '''
                INSERT INTO engagement_events 
                (email_send_id, event_type, event_time, user_agent, ip_address, clicked_url, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            '''
            params = (
                email_send_id, event_type, event_time, user_agent, ip_address, clicked_url,
                json.dumps(metadata) if metadata else None
            )
            
            self.db.execute(query, params)
            
        except Exception as e:
            logger.error(f"Error recording engagement event: {str(e)}")
    
    def get_campaign_stats(self, campaign_id: int) -> Dict[str, Any]:
        """Get engagement statistics for a campaign"""
        try:
            query = '''
                SELECT 
                    COUNT(*) as total_sent,
                    SUM(CASE WHEN delivered_time IS NOT NULL THEN 1 ELSE 0 END) as delivered,
                    SUM(CASE WHEN opened_time IS NOT NULL THEN 1 ELSE 0 END) as opened,
                    SUM(CASE WHEN clicked_time IS NOT NULL THEN 1 ELSE 0 END) as clicked,
                    SUM(CASE WHEN bounced_time IS NOT NULL THEN 1 ELSE 0 END) as bounced,
                    SUM(CASE WHEN complained_time IS NOT NULL THEN 1 ELSE 0 END) as complained,
                    SUM(CASE WHEN unsubscribed_time IS NOT NULL THEN 1 ELSE 0 END) as unsubscribed
                FROM email_sends 
                WHERE campaign_id = ?
            '''
            
            cursor = self.db.execute(query, (campaign_id,))
            row = cursor.fetchone()
            
            if row:
                stats = dict(row)
                total = stats['total_sent'] or 1  # Avoid division by zero
                
                # Calculate rates
                stats['delivery_rate'] = (stats['delivered'] / total) * 100
                stats['open_rate'] = (stats['opened'] / total) * 100
                stats['click_rate'] = (stats['clicked'] / total) * 100
                stats['bounce_rate'] = (stats['bounced'] / total) * 100
                stats['complaint_rate'] = (stats['complained'] / total) * 100
                stats['unsubscribe_rate'] = (stats['unsubscribed'] / total) * 100
                
                return stats
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting campaign stats for {campaign_id}: {str(e)}")
            return {}
    
    def get_subscriber_engagement_history(self, email: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get engagement history for a subscriber"""
        try:
            query = '''
                SELECT es.*, ee.event_type, ee.event_time, ee.clicked_url
                FROM email_sends es
                LEFT JOIN engagement_events ee ON es.id = ee.email_send_id
                WHERE es.email = ? AND es.sent_time >= datetime('now', '-{} days')
                ORDER BY es.sent_time DESC, ee.event_time DESC
            '''.format(days)
            
            cursor = self.db.execute(query, (email,))
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Error getting engagement history for {email}: {str(e)}")
            return []
