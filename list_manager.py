# list_manager.py
import csv
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from email_validator import validate_email, EmailNotValidError

from database.models import db

class SubscriberManager:
    def __init__(self, migrate_from_json: bool = True):
        # Migrate existing JSON data to database if requested
        if migrate_from_json:
            db.migrate_from_json()

    def validate_email_address(self, email: str) -> bool:
        """Validate email address format"""
        try:
            validated = validate_email(email)
            return True
        except EmailNotValidError:
            return False
            
    def add_subscriber(self, email: str, name: str, company: str = None,
                      source: str = None, segment: str = 'general') -> bool:
        """Add new subscriber to database"""
        if not self.validate_email_address(email):
            return False

        try:
            db.execute_update('''
                INSERT OR REPLACE INTO subscribers
                (email, name, company, source, segment, status, subscribed_date, last_engaged, engagement_score)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, 100.0)
            ''', (
                email.lower().strip(),
                name.strip(),
                company.strip() if company else None,
                source,
                segment,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            return True
        except Exception as e:
            print(f"Error adding subscriber: {e}")
            return False

    def unsubscribe(self, email: str) -> bool:
        """Mark subscriber as unsubscribed"""
        try:
            db.execute_update('''
                UPDATE subscribers
                SET status = 'unsubscribed',
                    unsubscribed_date = ?,
                    updated_at = ?
                WHERE email = ?
            ''', (
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                email.lower().strip()
            ))
            return True
        except Exception as e:
            print(f"Error unsubscribing {email}: {e}")
            return False

    def clean_list(self) -> List[Dict]:
        """Get clean list of active subscribers"""
        try:
            return db.execute_query('''
                SELECT id, email, name, company, segment, engagement_score, last_engaged
                FROM subscribers
                WHERE status = 'active'
                AND bounce_count < 3
                AND complaint_count = 0
                ORDER BY engagement_score DESC, last_engaged DESC
            ''')
        except Exception as e:
            print(f"Error getting clean list: {e}")
            return []

    def get_subscribers_by_segment(self, segment: str) -> List[Dict]:
        """Get subscribers by segment"""
        try:
            return db.execute_query('''
                SELECT id, email, name, company, segment, engagement_score
                FROM subscribers
                WHERE status = 'active' AND segment = ?
                ORDER BY engagement_score DESC
            ''', (segment,))
        except Exception as e:
            print(f"Error getting subscribers by segment: {e}")
            return []

    def get_high_engagement_subscribers(self, min_score: float = 80.0) -> List[Dict]:
        """Get subscribers with high engagement scores"""
        try:
            return db.execute_query('''
                SELECT id, email, name, company, engagement_score, last_engaged
                FROM subscribers
                WHERE status = 'active'
                AND engagement_score >= ?
                AND bounce_count < 2
                ORDER BY engagement_score DESC
            ''', (min_score,))
        except Exception as e:
            print(f"Error getting high engagement subscribers: {e}")
            return []

    def record_bounce(self, email: str, bounce_type: str, bounce_reason: str = None,
                     esp_provider: str = None, campaign_id: int = None):
        """Record email bounce"""
        try:
            # Record bounce in bounces table
            db.execute_update('''
                INSERT INTO bounces (email, bounce_type, bounce_reason, esp_provider, campaign_id, is_permanent)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                email.lower().strip(),
                bounce_type,
                bounce_reason,
                esp_provider,
                campaign_id,
                bounce_type.lower() in ['hard', 'permanent', 'suppress']
            ))

            # Update subscriber bounce count
            db.execute_update('''
                UPDATE subscribers
                SET bounce_count = bounce_count + 1,
                    status = CASE
                        WHEN bounce_count >= 2 AND ? IN ('hard', 'permanent', 'suppress') THEN 'bounced'
                        ELSE status
                    END,
                    updated_at = ?
                WHERE email = ?
            ''', (
                bounce_type.lower(),
                datetime.now().isoformat(),
                email.lower().strip()
            ))

        except Exception as e:
            print(f"Error recording bounce for {email}: {e}")

    def record_complaint(self, email: str, complaint_type: str = 'spam',
                        esp_provider: str = None, campaign_id: int = None):
        """Record spam complaint"""
        try:
            # Record complaint
            db.execute_update('''
                INSERT INTO complaints (email, complaint_type, esp_provider, campaign_id)
                VALUES (?, ?, ?, ?)
            ''', (
                email.lower().strip(),
                complaint_type,
                esp_provider,
                campaign_id
            ))

            # Update subscriber - complaints are serious, mark as unsubscribed
            db.execute_update('''
                UPDATE subscribers
                SET complaint_count = complaint_count + 1,
                    status = 'unsubscribed',
                    unsubscribed_date = ?,
                    updated_at = ?
                WHERE email = ?
            ''', (
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                email.lower().strip()
            ))

        except Exception as e:
            print(f"Error recording complaint for {email}: {e}")

    def update_engagement(self, email: str, engagement_type: str = 'open'):
        """Update subscriber engagement"""
        try:
            # Calculate engagement score boost
            score_boost = {'open': 2, 'click': 5, 'reply': 10}.get(engagement_type, 1)

            db.execute_update('''
                UPDATE subscribers
                SET last_engaged = ?,
                    engagement_score = MIN(100.0, engagement_score + ?),
                    updated_at = ?
                WHERE email = ?
            ''', (
                datetime.now().isoformat(),
                score_boost,
                datetime.now().isoformat(),
                email.lower().strip()
            ))

        except Exception as e:
            print(f"Error updating engagement for {email}: {e}")

    def get_subscriber_stats(self) -> Dict:
        """Get overall subscriber statistics"""
        try:
            stats = {}

            # Total counts by status
            status_counts = db.execute_query('''
                SELECT status, COUNT(*) as count
                FROM subscribers
                GROUP BY status
            ''')

            for row in status_counts:
                stats[f"{row['status']}_count"] = row['count']

            # Engagement statistics
            engagement_stats = db.execute_query('''
                SELECT
                    AVG(engagement_score) as avg_engagement,
                    COUNT(CASE WHEN engagement_score >= 80 THEN 1 END) as high_engagement,
                    COUNT(CASE WHEN last_engaged > datetime('now', '-30 days') THEN 1 END) as recently_engaged
                FROM subscribers
                WHERE status = 'active'
            ''')[0]

            stats.update(engagement_stats)

            # Recent activity
            recent_activity = db.execute_query('''
                SELECT
                    COUNT(CASE WHEN subscribed_date > datetime('now', '-7 days') THEN 1 END) as new_this_week,
                    COUNT(CASE WHEN unsubscribed_date > datetime('now', '-7 days') THEN 1 END) as unsubscribed_this_week
                FROM subscribers
            ''')[0]

            stats.update(recent_activity)

            return stats

        except Exception as e:
            print(f"Error getting subscriber stats: {e}")
            return {}