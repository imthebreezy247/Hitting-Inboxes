# src/database/subscriber_manager.py
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SubscriberManager:
    """
    Manages subscriber operations (legacy sync version)
    For async operations, use AsyncDatabaseManager directly
    """
    
    def __init__(self, db_session):
        self.db = db_session
    
    def add_subscriber(self, email: str, name: str, company: Optional[str] = None,
                      segment: str = "general", source: Optional[str] = None,
                      custom_fields: Optional[Dict] = None, tags: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Add a new subscriber"""
        try:
            # Check if subscriber already exists
            existing = self.get_subscriber(email)
            if existing:
                return False, "Subscriber already exists"
            
            # Insert new subscriber
            query = '''
                INSERT INTO subscribers (email, name, company, segment, source, custom_fields, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            '''
            params = (
                email, name, company, segment, source,
                json.dumps(custom_fields) if custom_fields else None,
                json.dumps(tags) if tags else None
            )
            
            cursor = self.db.execute(query, params)
            self.db.commit()
            
            logger.info(f"Added subscriber: {email}")
            return True, "Subscriber added successfully"
            
        except Exception as e:
            logger.error(f"Error adding subscriber {email}: {str(e)}")
            self.db.rollback()
            return False, f"Error adding subscriber: {str(e)}"
    
    def get_subscriber(self, email: str) -> Optional[Dict[str, Any]]:
        """Get subscriber by email"""
        try:
            query = "SELECT * FROM subscribers WHERE email = ? AND status = 'active'"
            cursor = self.db.execute(query, (email,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
            
        except Exception as e:
            logger.error(f"Error getting subscriber {email}: {str(e)}")
            return None
    
    def update_subscriber(self, email: str, **updates) -> Tuple[bool, str]:
        """Update subscriber information"""
        try:
            if not updates:
                return False, "No updates provided"
            
            # Build update query
            set_clauses = []
            params = []
            
            for field, value in updates.items():
                if field in ['name', 'company', 'segment', 'source']:
                    set_clauses.append(f"{field} = ?")
                    params.append(value)
                elif field in ['custom_fields', 'tags']:
                    set_clauses.append(f"{field} = ?")
                    params.append(json.dumps(value) if value else None)
            
            if not set_clauses:
                return False, "No valid fields to update"
            
            set_clauses.append("updated_at = ?")
            params.append(datetime.utcnow())
            params.append(email)
            
            query = f"UPDATE subscribers SET {', '.join(set_clauses)} WHERE email = ?"
            
            cursor = self.db.execute(query, params)
            self.db.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Updated subscriber: {email}")
                return True, "Subscriber updated successfully"
            else:
                return False, "Subscriber not found"
                
        except Exception as e:
            logger.error(f"Error updating subscriber {email}: {str(e)}")
            self.db.rollback()
            return False, f"Error updating subscriber: {str(e)}"
    
    def delete_subscriber(self, email: str) -> Tuple[bool, str]:
        """Soft delete subscriber (mark as inactive)"""
        try:
            query = "UPDATE subscribers SET status = 'inactive', updated_at = ? WHERE email = ?"
            params = (datetime.utcnow(), email)
            
            cursor = self.db.execute(query, params)
            self.db.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Deleted subscriber: {email}")
                return True, "Subscriber deleted successfully"
            else:
                return False, "Subscriber not found"
                
        except Exception as e:
            logger.error(f"Error deleting subscriber {email}: {str(e)}")
            self.db.rollback()
            return False, f"Error deleting subscriber: {str(e)}"
    
    def list_subscribers(self, limit: int = 100, offset: int = 0, 
                        segment: Optional[str] = None) -> List[Dict[str, Any]]:
        """List subscribers with pagination"""
        try:
            query = "SELECT * FROM subscribers WHERE status = 'active'"
            params = []
            
            if segment:
                query += " AND segment = ?"
                params.append(segment)
            
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor = self.db.execute(query, params)
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Error listing subscribers: {str(e)}")
            return []
    
    def get_subscriber_count(self, segment: Optional[str] = None) -> int:
        """Get total subscriber count"""
        try:
            query = "SELECT COUNT(*) as count FROM subscribers WHERE status = 'active'"
            params = []
            
            if segment:
                query += " AND segment = ?"
                params.append(segment)
            
            cursor = self.db.execute(query, params)
            row = cursor.fetchone()
            
            return row['count'] if row else 0
            
        except Exception as e:
            logger.error(f"Error getting subscriber count: {str(e)}")
            return 0
    
    def update_engagement_score(self, email: str, score: float) -> bool:
        """Update subscriber engagement score"""
        try:
            query = '''
                UPDATE subscribers 
                SET engagement_score = ?, last_engaged = ?, updated_at = ?
                WHERE email = ?
            '''
            params = (score, datetime.utcnow(), datetime.utcnow(), email)
            
            cursor = self.db.execute(query, params)
            self.db.commit()
            
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error updating engagement score for {email}: {str(e)}")
            self.db.rollback()
            return False
