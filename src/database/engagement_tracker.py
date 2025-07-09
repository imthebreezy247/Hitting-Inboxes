# src/database/engagement_tracker.py
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from .models import Engagement, Subscriber, Campaign
from .subscriber_manager import SubscriberManager

class EngagementTracker:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.subscriber_manager = SubscriberManager(db_session)
    
    def track_email_sent(self, subscriber_id: int, campaign_id: int, 
                        provider_used: str, message_id: str = None) -> int:
        """Track email sent event"""
        engagement = Engagement(
            subscriber_id=subscriber_id,
            campaign_id=campaign_id,
            provider_used=provider_used,
            message_id=message_id,
            sent_at=datetime.utcnow()
        )
        
        try:
            self.db.add(engagement)
            self.db.commit()
            
            # Update subscriber total sent count
            subscriber = self.db.query(Subscriber).filter_by(id=subscriber_id).first()
            if subscriber:
                subscriber.total_sent += 1
                self.db.commit()
            
            return engagement.id
        except Exception as e:
            self.db.rollback()
            print(f"Error tracking email sent: {e}")
            return None
    
    def track_delivery(self, engagement_id: int = None, message_id: str = None) -> bool:
        """Track email delivery"""
        engagement = self._get_engagement(engagement_id, message_id)
        if not engagement:
            return False
        
        engagement.delivered_at = datetime.utcnow()
        engagement.is_delivered = True
        
        try:
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Error tracking delivery: {e}")
            return False
    
    def track_open(self, engagement_id: int = None, message_id: str = None,
                  user_agent: str = None, ip_address: str = None) -> bool:
        """Track email open event"""
        engagement = self._get_engagement(engagement_id, message_id)
        if not engagement:
            return False
        
        # Only track first open
        if not engagement.is_opened:
            engagement.opened_at = datetime.utcnow()
            engagement.is_opened = True
            engagement.user_agent = user_agent
            engagement.ip_address = ip_address
            
            try:
                self.db.commit()
                
                # Update subscriber engagement
                self.subscriber_manager.update_engagement_score(
                    engagement.subscriber_id, 'open'
                )
                
                # Update campaign open count
                campaign = self.db.query(Campaign).filter_by(id=engagement.campaign_id).first()
                if campaign:
                    campaign.open_count += 1
                    if campaign.sent_count > 0:
                        campaign.open_rate = campaign.open_count / campaign.sent_count
                    self.db.commit()
                
                return True
            except Exception as e:
                self.db.rollback()
                print(f"Error tracking open: {e}")
                return False
        
        return True  # Already opened
    
    def track_click(self, engagement_id: int = None, message_id: str = None,
                   clicked_url: str = None, user_agent: str = None, 
                   ip_address: str = None) -> bool:
        """Track email click event"""
        engagement = self._get_engagement(engagement_id, message_id)
        if not engagement:
            return False
        
        # Track first click
        if not engagement.is_clicked:
            engagement.clicked_at = datetime.utcnow()
            engagement.is_clicked = True
            engagement.user_agent = user_agent or engagement.user_agent
            engagement.ip_address = ip_address or engagement.ip_address
            
            # Store click data
            if not engagement.tracking_data:
                engagement.tracking_data = {}
            engagement.tracking_data['clicked_url'] = clicked_url
            
            try:
                self.db.commit()
                
                # Update subscriber engagement
                self.subscriber_manager.update_engagement_score(
                    engagement.subscriber_id, 'click'
                )
                
                # Update campaign click count
                campaign = self.db.query(Campaign).filter_by(id=engagement.campaign_id).first()
                if campaign:
                    campaign.click_count += 1
                    if campaign.sent_count > 0:
                        campaign.click_rate = campaign.click_count / campaign.sent_count
                    self.db.commit()
                
                return True
            except Exception as e:
                self.db.rollback()
                print(f"Error tracking click: {e}")
                return False
        
        return True  # Already clicked
    
    def track_bounce(self, engagement_id: int = None, message_id: str = None,
                    bounce_type: str = 'hard', bounce_reason: str = None) -> bool:
        """Track email bounce event"""
        engagement = self._get_engagement(engagement_id, message_id)
        if not engagement:
            return False
        
        engagement.bounced_at = datetime.utcnow()
        engagement.is_bounced = True
        engagement.bounce_type = bounce_type
        engagement.bounce_reason = bounce_reason
        
        try:
            self.db.commit()
            
            # Update subscriber engagement
            self.subscriber_manager.update_engagement_score(
                engagement.subscriber_id, 'bounce'
            )
            
            # Update campaign bounce count
            campaign = self.db.query(Campaign).filter_by(id=engagement.campaign_id).first()
            if campaign:
                campaign.bounce_count += 1
                if campaign.sent_count > 0:
                    campaign.bounce_rate = campaign.bounce_count / campaign.sent_count
                self.db.commit()
            
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Error tracking bounce: {e}")
            return False
    
    def track_complaint(self, engagement_id: int = None, message_id: str = None,
                       complaint_type: str = 'spam') -> bool:
        """Track spam complaint event"""
        engagement = self._get_engagement(engagement_id, message_id)
        if not engagement:
            return False
        
        engagement.complained_at = datetime.utcnow()
        engagement.is_complained = True
        engagement.complaint_type = complaint_type
        
        try:
            self.db.commit()
            
            # Update subscriber engagement (severe penalty)
            self.subscriber_manager.update_engagement_score(
                engagement.subscriber_id, 'complaint'
            )
            
            # Update campaign complaint count
            campaign = self.db.query(Campaign).filter_by(id=engagement.campaign_id).first()
            if campaign:
                campaign.complaint_count += 1
                self.db.commit()
            
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Error tracking complaint: {e}")
            return False
    
    def track_unsubscribe(self, engagement_id: int = None, message_id: str = None,
                         email: str = None) -> bool:
        """Track unsubscribe event"""
        engagement = self._get_engagement(engagement_id, message_id)
        if not engagement:
            # If no engagement found but email provided, try to unsubscribe directly
            if email:
                return self.subscriber_manager.unsubscribe(email, 'campaign_unsubscribe')[0]
            return False
        
        engagement.unsubscribed_at = datetime.utcnow()
        
        try:
            self.db.commit()
            
            # Unsubscribe the subscriber
            subscriber = self.db.query(Subscriber).filter_by(id=engagement.subscriber_id).first()
            if subscriber:
                self.subscriber_manager.unsubscribe(subscriber.email, 'campaign_unsubscribe')
            
            # Update campaign unsubscribe count
            campaign = self.db.query(Campaign).filter_by(id=engagement.campaign_id).first()
            if campaign:
                campaign.unsubscribe_count += 1
                self.db.commit()
            
            return True
        except Exception as e:
            self.db.rollback()
            print(f"Error tracking unsubscribe: {e}")
            return False
    
    def _get_engagement(self, engagement_id: int = None, 
                      message_id: str = None) -> Optional[Engagement]:
        """Get engagement record by ID or message ID"""
        if engagement_id:
            return self.db.query(Engagement).filter_by(id=engagement_id).first()
        elif message_id:
            return self.db.query(Engagement).filter_by(message_id=message_id).first()
        return None
    
    def get_campaign_engagement_stats(self, campaign_id: int) -> Dict:
        """Get detailed engagement statistics for a campaign"""
        try:
            campaign = self.db.query(Campaign).filter_by(id=campaign_id).first()
            if not campaign:
                return {}
            
            # Get engagement counts
            engagements = self.db.query(Engagement).filter_by(campaign_id=campaign_id)
            
            total_sent = engagements.count()
            delivered = engagements.filter_by(is_delivered=True).count()
            opened = engagements.filter_by(is_opened=True).count()
            clicked = engagements.filter_by(is_clicked=True).count()
            bounced = engagements.filter_by(is_bounced=True).count()
            complained = engagements.filter_by(is_complained=True).count()
            
            # Calculate rates
            delivery_rate = (delivered / total_sent * 100) if total_sent > 0 else 0
            open_rate = (opened / delivered * 100) if delivered > 0 else 0
            click_rate = (clicked / delivered * 100) if delivered > 0 else 0
            bounce_rate = (bounced / total_sent * 100) if total_sent > 0 else 0
            complaint_rate = (complained / total_sent * 100) if total_sent > 0 else 0
            
            # Provider breakdown
            provider_stats = self.db.query(
                Engagement.provider_used,
                func.count(Engagement.id).label('sent'),
                func.sum(func.cast(Engagement.is_delivered, func.Integer)).label('delivered'),
                func.sum(func.cast(Engagement.is_opened, func.Integer)).label('opened'),
                func.sum(func.cast(Engagement.is_clicked, func.Integer)).label('clicked'),
                func.sum(func.cast(Engagement.is_bounced, func.Integer)).label('bounced')
            ).filter_by(campaign_id=campaign_id).group_by(Engagement.provider_used).all()
            
            return {
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'sent_time': campaign.sent_time,
                'totals': {
                    'sent': total_sent,
                    'delivered': delivered,
                    'opened': opened,
                    'clicked': clicked,
                    'bounced': bounced,
                    'complained': complained
                },
                'rates': {
                    'delivery_rate': round(delivery_rate, 2),
                    'open_rate': round(open_rate, 2),
                    'click_rate': round(click_rate, 2),
                    'bounce_rate': round(bounce_rate, 2),
                    'complaint_rate': round(complaint_rate, 4)
                },
                'provider_breakdown': [
                    {
                        'provider': stat.provider_used,
                        'sent': stat.sent,
                        'delivered': stat.delivered or 0,
                        'opened': stat.opened or 0,
                        'clicked': stat.clicked or 0,
                        'bounced': stat.bounced or 0,
                        'delivery_rate': round((stat.delivered or 0) / stat.sent * 100, 2) if stat.sent > 0 else 0
                    }
                    for stat in provider_stats
                ]
            }
            
        except Exception as e:
            print(f"Error getting campaign engagement stats: {e}")
            return {}
    
    def get_subscriber_engagement_history(self, subscriber_id: int, 
                                        limit: int = 50) -> List[Dict]:
        """Get engagement history for a subscriber"""
        try:
            engagements = self.db.query(Engagement).filter_by(
                subscriber_id=subscriber_id
            ).order_by(desc(Engagement.sent_at)).limit(limit).all()
            
            history = []
            for eng in engagements:
                campaign = self.db.query(Campaign).filter_by(id=eng.campaign_id).first()
                
                history.append({
                    'engagement_id': eng.id,
                    'campaign_name': campaign.name if campaign else 'Unknown',
                    'campaign_subject': campaign.subject if campaign else 'Unknown',
                    'provider_used': eng.provider_used,
                    'sent_at': eng.sent_at,
                    'delivered_at': eng.delivered_at,
                    'opened_at': eng.opened_at,
                    'clicked_at': eng.clicked_at,
                    'bounced_at': eng.bounced_at,
                    'bounce_type': eng.bounce_type,
                    'bounce_reason': eng.bounce_reason,
                    'is_delivered': eng.is_delivered,
                    'is_opened': eng.is_opened,
                    'is_clicked': eng.is_clicked,
                    'is_bounced': eng.is_bounced,
                    'is_complained': eng.is_complained
                })
            
            return history
            
        except Exception as e:
            print(f"Error getting subscriber engagement history: {e}")
            return []
    
    def get_engagement_trends(self, days: int = 30) -> Dict:
        """Get engagement trends over specified period"""
        try:
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Daily engagement stats
            daily_stats = self.db.query(
                func.date(Engagement.sent_at).label('date'),
                func.count(Engagement.id).label('sent'),
                func.sum(func.cast(Engagement.is_delivered, func.Integer)).label('delivered'),
                func.sum(func.cast(Engagement.is_opened, func.Integer)).label('opened'),
                func.sum(func.cast(Engagement.is_clicked, func.Integer)).label('clicked'),
                func.sum(func.cast(Engagement.is_bounced, func.Integer)).label('bounced')
            ).filter(
                Engagement.sent_at >= start_date
            ).group_by(
                func.date(Engagement.sent_at)
            ).order_by(
                func.date(Engagement.sent_at)
            ).all()
            
            trends = []
            for stat in daily_stats:
                sent = stat.sent or 0
                delivered = stat.delivered or 0
                opened = stat.opened or 0
                clicked = stat.clicked or 0
                bounced = stat.bounced or 0
                
                trends.append({
                    'date': stat.date.isoformat(),
                    'sent': sent,
                    'delivered': delivered,
                    'opened': opened,
                    'clicked': clicked,
                    'bounced': bounced,
                    'delivery_rate': round(delivered / sent * 100, 2) if sent > 0 else 0,
                    'open_rate': round(opened / delivered * 100, 2) if delivered > 0 else 0,
                    'click_rate': round(clicked / delivered * 100, 2) if delivered > 0 else 0,
                    'bounce_rate': round(bounced / sent * 100, 2) if sent > 0 else 0
                })
            
            return {
                'period_days': days,
                'start_date': start_date.isoformat(),
                'end_date': datetime.utcnow().isoformat(),
                'daily_trends': trends
            }
            
        except Exception as e:
            print(f"Error getting engagement trends: {e}")
            return {}
