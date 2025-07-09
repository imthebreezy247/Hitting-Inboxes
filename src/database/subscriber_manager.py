# src/database/subscriber_manager.py
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from .models import Subscriber, Engagement, Campaign
from email_validator import validate_email, EmailNotValidError

class SubscriberManager:
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def add_subscriber(self, email: str, name: str, company: str = None, 
                      segment: str = 'general', source: str = None, 
                      custom_fields: Dict = None, tags: List[str] = None) -> Tuple[bool, str]:
        """Add new subscriber with validation"""
        
        # Validate email
        try:
            validated_email = validate_email(email)
            email = validated_email.email.lower()
        except EmailNotValidError as e:
            return False, f"Invalid email address: {str(e)}"
        
        # Check if subscriber already exists
        existing = self.db.query(Subscriber).filter_by(email=email).first()
        if existing:
            if existing.status == 'unsubscribed':
                # Reactivate unsubscribed user
                existing.status = 'active'
                existing.subscribed_date = datetime.utcnow()
                existing.unsubscribed_date = None
                existing.updated_at = datetime.utcnow()
                self.db.commit()
                return True, "Subscriber reactivated"
            else:
                return False, "Subscriber already exists"
        
        # Create new subscriber
        subscriber = Subscriber(
            email=email,
            name=name.strip() if name else '',
            company=company.strip() if company else None,
            segment=segment,
            source=source,
            custom_fields=custom_fields or {},
            tags=tags or [],
            engagement_score=0.5,  # Start with neutral score
            subscribed_date=datetime.utcnow()
        )
        
        try:
            self.db.add(subscriber)
            self.db.commit()
            return True, "Subscriber added successfully"
        except Exception as e:
            self.db.rollback()
            return False, f"Database error: {str(e)}"
    
    def update_subscriber(self, email: str, **kwargs) -> Tuple[bool, str]:
        """Update subscriber information"""
        subscriber = self.db.query(Subscriber).filter_by(email=email.lower()).first()
        if not subscriber:
            return False, "Subscriber not found"
        
        # Update allowed fields
        allowed_fields = ['name', 'company', 'segment', 'custom_fields', 'tags', 'time_zone']
        
        for field, value in kwargs.items():
            if field in allowed_fields and hasattr(subscriber, field):
                setattr(subscriber, field, value)
        
        subscriber.updated_at = datetime.utcnow()
        
        try:
            self.db.commit()
            return True, "Subscriber updated successfully"
        except Exception as e:
            self.db.rollback()
            return False, f"Update failed: {str(e)}"
    
    def unsubscribe(self, email: str, reason: str = None) -> Tuple[bool, str]:
        """Unsubscribe a subscriber"""
        subscriber = self.db.query(Subscriber).filter_by(email=email.lower()).first()
        if not subscriber:
            return False, "Subscriber not found"
        
        if subscriber.status == 'unsubscribed':
            return True, "Already unsubscribed"
        
        subscriber.status = 'unsubscribed'
        subscriber.unsubscribed_date = datetime.utcnow()
        subscriber.updated_at = datetime.utcnow()
        
        # Add reason to custom fields if provided
        if reason:
            if not subscriber.custom_fields:
                subscriber.custom_fields = {}
            subscriber.custom_fields['unsubscribe_reason'] = reason
        
        try:
            self.db.commit()
            return True, "Subscriber unsubscribed successfully"
        except Exception as e:
            self.db.rollback()
            return False, f"Unsubscribe failed: {str(e)}"
    
    def get_subscriber(self, email: str) -> Optional[Dict]:
        """Get subscriber by email"""
        subscriber = self.db.query(Subscriber).filter_by(email=email.lower()).first()
        if not subscriber:
            return None
        
        return {
            'id': subscriber.id,
            'email': subscriber.email,
            'name': subscriber.name,
            'company': subscriber.company,
            'status': subscriber.status,
            'segment': subscriber.segment,
            'engagement_score': subscriber.engagement_score,
            'total_sent': subscriber.total_sent,
            'total_opens': subscriber.total_opens,
            'total_clicks': subscriber.total_clicks,
            'bounce_count': subscriber.bounce_count,
            'complaint_count': subscriber.complaint_count,
            'last_open': subscriber.last_open,
            'last_click': subscriber.last_click,
            'subscribed_date': subscriber.subscribed_date,
            'custom_fields': subscriber.custom_fields,
            'tags': subscriber.tags
        }
    
    def get_subscribers_by_segment(self, segment: str, limit: int = None, 
                                  min_engagement: float = None) -> List[Dict]:
        """Get subscribers by segment with optional filters"""
        query = self.db.query(Subscriber).filter(
            and_(
                Subscriber.status == 'active',
                Subscriber.segment == segment
            )
        )
        
        if min_engagement is not None:
            query = query.filter(Subscriber.engagement_score >= min_engagement)
        
        # Order by engagement score
        query = query.order_by(Subscriber.engagement_score.desc())
        
        if limit:
            query = query.limit(limit)
        
        subscribers = query.all()
        
        return [
            {
                'id': sub.id,
                'email': sub.email,
                'name': sub.name,
                'company': sub.company,
                'engagement_score': sub.engagement_score,
                'last_open': sub.last_open,
                'custom_fields': sub.custom_fields or {}
            }
            for sub in subscribers
        ]
    
    def update_engagement_score(self, subscriber_id: int, event_type: str):
        """Update subscriber engagement score based on event"""
        subscriber = self.db.query(Subscriber).filter_by(id=subscriber_id).first()
        if not subscriber:
            return
        
        # Score adjustments
        score_changes = {
            'open': 0.02,
            'click': 0.05,
            'reply': 0.10,
            'forward': 0.08,
            'bounce': -0.10,
            'complaint': -0.50,
            'unsubscribe': -0.30
        }
        
        change = score_changes.get(event_type, 0)
        old_score = subscriber.engagement_score
        
        # Update score (keep between 0 and 1)
        subscriber.engagement_score = max(0.0, min(1.0, subscriber.engagement_score + change))
        
        # Update counters
        if event_type == 'open':
            subscriber.total_opens += 1
            subscriber.last_open = datetime.utcnow()
        elif event_type == 'click':
            subscriber.total_clicks += 1
            subscriber.last_click = datetime.utcnow()
        elif event_type == 'bounce':
            subscriber.bounce_count += 1
        elif event_type == 'complaint':
            subscriber.complaint_count += 1
            subscriber.status = 'complained'  # Automatically mark as complained
        
        subscriber.updated_at = datetime.utcnow()
        
        try:
            self.db.commit()
            print(f"Updated engagement for {subscriber.email}: {old_score:.3f} → {subscriber.engagement_score:.3f}")
        except Exception as e:
            self.db.rollback()
            print(f"Error updating engagement: {e}")
    
    def get_engagement_statistics(self) -> Dict:
        """Get overall engagement statistics"""
        try:
            # Basic counts
            total_subscribers = self.db.query(Subscriber).count()
            active_subscribers = self.db.query(Subscriber).filter_by(status='active').count()
            
            # Engagement metrics
            avg_engagement = self.db.query(func.avg(Subscriber.engagement_score)).filter_by(status='active').scalar() or 0
            
            # Segment breakdown
            segment_stats = self.db.query(
                Subscriber.segment,
                func.count(Subscriber.id).label('count'),
                func.avg(Subscriber.engagement_score).label('avg_engagement')
            ).filter_by(status='active').group_by(Subscriber.segment).all()
            
            # Recent activity (last 30 days)
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            recent_opens = self.db.query(Subscriber).filter(
                and_(
                    Subscriber.status == 'active',
                    Subscriber.last_open >= thirty_days_ago
                )
            ).count()
            
            recent_clicks = self.db.query(Subscriber).filter(
                and_(
                    Subscriber.status == 'active',
                    Subscriber.last_click >= thirty_days_ago
                )
            ).count()
            
            return {
                'total_subscribers': total_subscribers,
                'active_subscribers': active_subscribers,
                'average_engagement_score': round(avg_engagement, 3),
                'recent_opens_30d': recent_opens,
                'recent_clicks_30d': recent_clicks,
                'engagement_rate_30d': round((recent_opens / active_subscribers * 100), 2) if active_subscribers > 0 else 0,
                'click_rate_30d': round((recent_clicks / active_subscribers * 100), 2) if active_subscribers > 0 else 0,
                'segments': [
                    {
                        'segment': stat.segment,
                        'count': stat.count,
                        'avg_engagement': round(stat.avg_engagement, 3)
                    }
                    for stat in segment_stats
                ]
            }
            
        except Exception as e:
            print(f"Error getting engagement statistics: {e}")
            return {}
    
    def clean_list(self, remove_bounced: bool = True, remove_complained: bool = True,
                  min_engagement: float = None, days_inactive: int = None) -> Dict:
        """Clean subscriber list based on criteria"""
        
        cleaned_count = 0
        
        try:
            # Build query for subscribers to clean
            query = self.db.query(Subscriber).filter_by(status='active')
            
            conditions = []
            
            if remove_bounced:
                conditions.append(Subscriber.bounce_count >= 3)
            
            if remove_complained:
                conditions.append(Subscriber.complaint_count > 0)
            
            if min_engagement is not None:
                conditions.append(Subscriber.engagement_score < min_engagement)
            
            if days_inactive is not None:
                cutoff_date = datetime.utcnow() - timedelta(days=days_inactive)
                conditions.append(
                    or_(
                        Subscriber.last_open < cutoff_date,
                        Subscriber.last_open.is_(None)
                    )
                )
            
            if conditions:
                # Mark subscribers as inactive instead of deleting
                subscribers_to_clean = query.filter(or_(*conditions)).all()
                
                for subscriber in subscribers_to_clean:
                    if subscriber.bounce_count >= 3:
                        subscriber.status = 'bounced'
                    elif subscriber.complaint_count > 0:
                        subscriber.status = 'complained'
                    else:
                        subscriber.status = 'inactive'
                    
                    subscriber.updated_at = datetime.utcnow()
                    cleaned_count += 1
                
                self.db.commit()
            
            return {
                'success': True,
                'cleaned_count': cleaned_count,
                'message': f"Cleaned {cleaned_count} subscribers"
            }
            
        except Exception as e:
            self.db.rollback()
            return {
                'success': False,
                'cleaned_count': 0,
                'message': f"Cleaning failed: {str(e)}"
            }
    
    def bulk_import(self, subscribers_data: List[Dict]) -> Dict:
        """Bulk import subscribers"""
        added_count = 0
        updated_count = 0
        errors = []
        
        for data in subscribers_data:
            try:
                email = data.get('email', '').lower().strip()
                if not email:
                    errors.append("Missing email address")
                    continue
                
                # Validate email
                try:
                    validated_email = validate_email(email)
                    email = validated_email.email
                except EmailNotValidError:
                    errors.append(f"Invalid email: {email}")
                    continue
                
                # Check if exists
                existing = self.db.query(Subscriber).filter_by(email=email).first()
                
                if existing:
                    # Update existing
                    existing.name = data.get('name', existing.name)
                    existing.company = data.get('company', existing.company)
                    existing.segment = data.get('segment', existing.segment)
                    existing.updated_at = datetime.utcnow()
                    updated_count += 1
                else:
                    # Create new
                    subscriber = Subscriber(
                        email=email,
                        name=data.get('name', ''),
                        company=data.get('company'),
                        segment=data.get('segment', 'general'),
                        source=data.get('source', 'bulk_import'),
                        custom_fields=data.get('custom_fields', {}),
                        engagement_score=0.5
                    )
                    self.db.add(subscriber)
                    added_count += 1
                    
            except Exception as e:
                errors.append(f"Error processing {data.get('email', 'unknown')}: {str(e)}")
        
        try:
            self.db.commit()
            return {
                'success': True,
                'added': added_count,
                'updated': updated_count,
                'errors': errors
            }
        except Exception as e:
            self.db.rollback()
            return {
                'success': False,
                'added': 0,
                'updated': 0,
                'errors': [f"Database commit failed: {str(e)}"]
            }
