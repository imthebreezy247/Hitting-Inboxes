# src/utils/analytics.py
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json

from ..database.models import Campaign, Subscriber, Engagement, ProviderPerformance

class AnalyticsEngine:
    """Advanced analytics for email campaigns and subscriber behavior"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def get_campaign_performance_report(self, campaign_id: int) -> Dict:
        """Generate comprehensive campaign performance report"""
        campaign = self.db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            return {}
        
        # Basic metrics
        engagements = self.db.query(Engagement).filter_by(campaign_id=campaign_id)
        
        total_sent = engagements.count()
        delivered = engagements.filter_by(is_delivered=True).count()
        opened = engagements.filter_by(is_opened=True).count()
        clicked = engagements.filter_by(is_clicked=True).count()
        bounced = engagements.filter_by(is_bounced=True).count()
        complained = engagements.filter_by(is_complained=True).count()
        
        # Time-based analysis
        hourly_stats = self._get_hourly_engagement_stats(campaign_id)
        
        # Provider performance
        provider_stats = self._get_provider_performance_for_campaign(campaign_id)
        
        # Subscriber segment analysis
        segment_stats = self._get_segment_performance_for_campaign(campaign_id)
        
        # Engagement timeline
        engagement_timeline = self._get_engagement_timeline(campaign_id)
        
        return {
            'campaign_info': {
                'id': campaign.id,
                'name': campaign.name,
                'subject': campaign.subject,
                'sent_time': campaign.sent_time,
                'status': campaign.status
            },
            'overall_metrics': {
                'total_sent': total_sent,
                'delivered': delivered,
                'opened': opened,
                'clicked': clicked,
                'bounced': bounced,
                'complained': complained,
                'delivery_rate': round((delivered / total_sent * 100), 2) if total_sent > 0 else 0,
                'open_rate': round((opened / delivered * 100), 2) if delivered > 0 else 0,
                'click_rate': round((clicked / delivered * 100), 2) if delivered > 0 else 0,
                'bounce_rate': round((bounced / total_sent * 100), 2) if total_sent > 0 else 0,
                'complaint_rate': round((complained / total_sent * 100), 4) if total_sent > 0 else 0
            },
            'time_analysis': {
                'hourly_stats': hourly_stats,
                'engagement_timeline': engagement_timeline
            },
            'provider_performance': provider_stats,
            'segment_analysis': segment_stats,
            'recommendations': self._generate_campaign_recommendations(campaign_id)
        }
    
    def _get_hourly_engagement_stats(self, campaign_id: int) -> List[Dict]:
        """Get hourly engagement statistics"""
        hourly_data = self.db.query(
            func.extract('hour', Engagement.sent_at).label('hour'),
            func.count(Engagement.id).label('sent'),
            func.sum(func.cast(Engagement.is_delivered, func.Integer)).label('delivered'),
            func.sum(func.cast(Engagement.is_opened, func.Integer)).label('opened'),
            func.sum(func.cast(Engagement.is_clicked, func.Integer)).label('clicked')
        ).filter_by(campaign_id=campaign_id).group_by(
            func.extract('hour', Engagement.sent_at)
        ).order_by('hour').all()
        
        return [
            {
                'hour': int(stat.hour),
                'sent': stat.sent,
                'delivered': stat.delivered or 0,
                'opened': stat.opened or 0,
                'clicked': stat.clicked or 0,
                'open_rate': round((stat.opened or 0) / (stat.delivered or 1) * 100, 2),
                'click_rate': round((stat.clicked or 0) / (stat.delivered or 1) * 100, 2)
            }
            for stat in hourly_data
        ]
    
    def _get_provider_performance_for_campaign(self, campaign_id: int) -> List[Dict]:
        """Get provider performance for specific campaign"""
        provider_data = self.db.query(
            Engagement.provider_used,
            func.count(Engagement.id).label('sent'),
            func.sum(func.cast(Engagement.is_delivered, func.Integer)).label('delivered'),
            func.sum(func.cast(Engagement.is_opened, func.Integer)).label('opened'),
            func.sum(func.cast(Engagement.is_clicked, func.Integer)).label('clicked'),
            func.sum(func.cast(Engagement.is_bounced, func.Integer)).label('bounced'),
            func.sum(func.cast(Engagement.is_complained, func.Integer)).label('complained')
        ).filter_by(campaign_id=campaign_id).group_by(
            Engagement.provider_used
        ).all()
        
        return [
            {
                'provider': stat.provider_used,
                'sent': stat.sent,
                'delivered': stat.delivered or 0,
                'opened': stat.opened or 0,
                'clicked': stat.clicked or 0,
                'bounced': stat.bounced or 0,
                'complained': stat.complained or 0,
                'delivery_rate': round((stat.delivered or 0) / stat.sent * 100, 2),
                'open_rate': round((stat.opened or 0) / (stat.delivered or 1) * 100, 2),
                'click_rate': round((stat.clicked or 0) / (stat.delivered or 1) * 100, 2),
                'bounce_rate': round((stat.bounced or 0) / stat.sent * 100, 2)
            }
            for stat in provider_data
        ]
    
    def _get_segment_performance_for_campaign(self, campaign_id: int) -> List[Dict]:
        """Get performance by subscriber segment"""
        segment_data = self.db.query(
            Subscriber.segment,
            func.count(Engagement.id).label('sent'),
            func.sum(func.cast(Engagement.is_delivered, func.Integer)).label('delivered'),
            func.sum(func.cast(Engagement.is_opened, func.Integer)).label('opened'),
            func.sum(func.cast(Engagement.is_clicked, func.Integer)).label('clicked'),
            func.avg(Subscriber.engagement_score).label('avg_engagement_score')
        ).join(
            Engagement, Subscriber.id == Engagement.subscriber_id
        ).filter(
            Engagement.campaign_id == campaign_id
        ).group_by(Subscriber.segment).all()
        
        return [
            {
                'segment': stat.segment,
                'sent': stat.sent,
                'delivered': stat.delivered or 0,
                'opened': stat.opened or 0,
                'clicked': stat.clicked or 0,
                'avg_engagement_score': round(stat.avg_engagement_score or 0, 3),
                'open_rate': round((stat.opened or 0) / (stat.delivered or 1) * 100, 2),
                'click_rate': round((stat.clicked or 0) / (stat.delivered or 1) * 100, 2)
            }
            for stat in segment_data
        ]
    
    def _get_engagement_timeline(self, campaign_id: int) -> Dict:
        """Get engagement timeline showing when opens/clicks occurred"""
        # Get opens over time (first 24 hours)
        opens_timeline = self.db.query(
            func.extract('hour', Engagement.opened_at).label('hour_after_send'),
            func.count(Engagement.id).label('opens')
        ).filter(
            and_(
                Engagement.campaign_id == campaign_id,
                Engagement.is_opened == True,
                Engagement.opened_at.isnot(None)
            )
        ).group_by(
            func.extract('hour', Engagement.opened_at)
        ).order_by('hour_after_send').all()
        
        # Get clicks over time
        clicks_timeline = self.db.query(
            func.extract('hour', Engagement.clicked_at).label('hour_after_send'),
            func.count(Engagement.id).label('clicks')
        ).filter(
            and_(
                Engagement.campaign_id == campaign_id,
                Engagement.is_clicked == True,
                Engagement.clicked_at.isnot(None)
            )
        ).group_by(
            func.extract('hour', Engagement.clicked_at)
        ).order_by('hour_after_send').all()
        
        return {
            'opens_by_hour': [
                {'hour': int(stat.hour_after_send), 'opens': stat.opens}
                for stat in opens_timeline
            ],
            'clicks_by_hour': [
                {'hour': int(stat.hour_after_send), 'clicks': stat.clicks}
                for stat in clicks_timeline
            ]
        }
    
    def _generate_campaign_recommendations(self, campaign_id: int) -> List[str]:
        """Generate recommendations based on campaign performance"""
        recommendations = []
        
        # Get campaign metrics
        engagements = self.db.query(Engagement).filter_by(campaign_id=campaign_id)
        total_sent = engagements.count()
        
        if total_sent == 0:
            return ["No data available for recommendations"]
        
        delivered = engagements.filter_by(is_delivered=True).count()
        opened = engagements.filter_by(is_opened=True).count()
        clicked = engagements.filter_by(is_clicked=True).count()
        bounced = engagements.filter_by(is_bounced=True).count()
        
        delivery_rate = delivered / total_sent
        open_rate = opened / delivered if delivered > 0 else 0
        click_rate = clicked / delivered if delivered > 0 else 0
        bounce_rate = bounced / total_sent
        
        # Delivery rate recommendations
        if delivery_rate < 0.95:
            recommendations.append("Low delivery rate detected. Consider list cleaning and authentication improvements.")
        
        # Open rate recommendations
        if open_rate < 0.15:
            recommendations.append("Low open rate. Consider A/B testing subject lines and send time optimization.")
        elif open_rate > 0.25:
            recommendations.append("Excellent open rate! Consider using similar subject line strategies in future campaigns.")
        
        # Click rate recommendations
        if click_rate < 0.02:
            recommendations.append("Low click rate. Review email content, call-to-action placement, and link relevance.")
        elif click_rate > 0.05:
            recommendations.append("Great click rate! Analyze successful content elements for future campaigns.")
        
        # Bounce rate recommendations
        if bounce_rate > 0.05:
            recommendations.append("High bounce rate detected. Implement more aggressive list cleaning and validation.")
        
        # Provider-specific recommendations
        provider_stats = self._get_provider_performance_for_campaign(campaign_id)
        if len(provider_stats) > 1:
            best_provider = max(provider_stats, key=lambda x: x['delivery_rate'])
            worst_provider = min(provider_stats, key=lambda x: x['delivery_rate'])
            
            if best_provider['delivery_rate'] - worst_provider['delivery_rate'] > 10:
                recommendations.append(f"Consider increasing volume through {best_provider['provider']} (better performance) and reducing {worst_provider['provider']} usage.")
        
        return recommendations
    
    def get_subscriber_lifecycle_analysis(self, days: int = 90) -> Dict:
        """Analyze subscriber lifecycle and engagement patterns"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Subscriber acquisition trends
        acquisition_trends = self.db.query(
            func.date(Subscriber.subscribed_date).label('date'),
            func.count(Subscriber.id).label('new_subscribers')
        ).filter(
            Subscriber.subscribed_date >= cutoff_date
        ).group_by(
            func.date(Subscriber.subscribed_date)
        ).order_by('date').all()
        
        # Engagement score distribution
        engagement_distribution = self.db.query(
            func.case([
                (Subscriber.engagement_score >= 0.8, 'High (0.8+)'),
                (Subscriber.engagement_score >= 0.5, 'Medium (0.5-0.8)'),
                (Subscriber.engagement_score >= 0.2, 'Low (0.2-0.5)'),
            ], else_='Very Low (<0.2)').label('engagement_level'),
            func.count(Subscriber.id).label('count')
        ).filter(
            Subscriber.status == 'active'
        ).group_by('engagement_level').all()
        
        # Churn analysis (subscribers who haven't engaged recently)
        churn_analysis = self.db.query(
            func.case([
                (Subscriber.last_open >= datetime.utcnow() - timedelta(days=7), 'Active (< 7 days)'),
                (Subscriber.last_open >= datetime.utcnow() - timedelta(days=30), 'Recent (7-30 days)'),
                (Subscriber.last_open >= datetime.utcnow() - timedelta(days=90), 'Inactive (30-90 days)'),
            ], else_='Dormant (90+ days)').label('activity_level'),
            func.count(Subscriber.id).label('count')
        ).filter(
            Subscriber.status == 'active'
        ).group_by('activity_level').all()
        
        return {
            'analysis_period_days': days,
            'acquisition_trends': [
                {
                    'date': stat.date.isoformat(),
                    'new_subscribers': stat.new_subscribers
                }
                for stat in acquisition_trends
            ],
            'engagement_distribution': [
                {
                    'level': stat.engagement_level,
                    'count': stat.count
                }
                for stat in engagement_distribution
            ],
            'churn_analysis': [
                {
                    'activity_level': stat.activity_level,
                    'count': stat.count
                }
                for stat in churn_analysis
            ]
        }
    
    def get_provider_comparison_report(self, days: int = 30) -> Dict:
        """Compare provider performance over time"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Daily provider performance
        daily_performance = self.db.query(
            func.date(Engagement.sent_at).label('date'),
            Engagement.provider_used,
            func.count(Engagement.id).label('sent'),
            func.sum(func.cast(Engagement.is_delivered, func.Integer)).label('delivered'),
            func.sum(func.cast(Engagement.is_opened, func.Integer)).label('opened'),
            func.sum(func.cast(Engagement.is_clicked, func.Integer)).label('clicked'),
            func.sum(func.cast(Engagement.is_bounced, func.Integer)).label('bounced')
        ).filter(
            Engagement.sent_at >= cutoff_date
        ).group_by(
            func.date(Engagement.sent_at),
            Engagement.provider_used
        ).order_by('date', Engagement.provider_used).all()
        
        # Aggregate provider stats
        provider_totals = {}
        daily_data = {}
        
        for stat in daily_performance:
            provider = stat.provider_used
            date_str = stat.date.isoformat()
            
            # Aggregate totals
            if provider not in provider_totals:
                provider_totals[provider] = {
                    'sent': 0, 'delivered': 0, 'opened': 0, 
                    'clicked': 0, 'bounced': 0
                }
            
            provider_totals[provider]['sent'] += stat.sent
            provider_totals[provider]['delivered'] += stat.delivered or 0
            provider_totals[provider]['opened'] += stat.opened or 0
            provider_totals[provider]['clicked'] += stat.clicked or 0
            provider_totals[provider]['bounced'] += stat.bounced or 0
            
            # Daily data
            if date_str not in daily_data:
                daily_data[date_str] = {}
            
            daily_data[date_str][provider] = {
                'sent': stat.sent,
                'delivered': stat.delivered or 0,
                'opened': stat.opened or 0,
                'clicked': stat.clicked or 0,
                'bounced': stat.bounced or 0,
                'delivery_rate': round((stat.delivered or 0) / stat.sent * 100, 2),
                'open_rate': round((stat.opened or 0) / (stat.delivered or 1) * 100, 2),
                'click_rate': round((stat.clicked or 0) / (stat.delivered or 1) * 100, 2)
            }
        
        # Calculate aggregate rates
        provider_summary = {}
        for provider, totals in provider_totals.items():
            provider_summary[provider] = {
                **totals,
                'delivery_rate': round(totals['delivered'] / totals['sent'] * 100, 2) if totals['sent'] > 0 else 0,
                'open_rate': round(totals['opened'] / totals['delivered'] * 100, 2) if totals['delivered'] > 0 else 0,
                'click_rate': round(totals['clicked'] / totals['delivered'] * 100, 2) if totals['delivered'] > 0 else 0,
                'bounce_rate': round(totals['bounced'] / totals['sent'] * 100, 2) if totals['sent'] > 0 else 0
            }
        
        return {
            'analysis_period_days': days,
            'provider_summary': provider_summary,
            'daily_performance': daily_data,
            'recommendations': self._generate_provider_recommendations(provider_summary)
        }
    
    def _generate_provider_recommendations(self, provider_summary: Dict) -> List[str]:
        """Generate recommendations based on provider performance"""
        recommendations = []
        
        if not provider_summary:
            return recommendations
        
        # Find best and worst performing providers
        providers = list(provider_summary.keys())
        if len(providers) < 2:
            return recommendations
        
        best_delivery = max(providers, key=lambda p: provider_summary[p]['delivery_rate'])
        worst_delivery = min(providers, key=lambda p: provider_summary[p]['delivery_rate'])
        
        best_open = max(providers, key=lambda p: provider_summary[p]['open_rate'])
        
        # Delivery rate recommendations
        if provider_summary[best_delivery]['delivery_rate'] - provider_summary[worst_delivery]['delivery_rate'] > 5:
            recommendations.append(f"Consider shifting more volume to {best_delivery} (better delivery rate: {provider_summary[best_delivery]['delivery_rate']:.1f}%)")
        
        # Open rate recommendations
        if provider_summary[best_open]['open_rate'] > 20:
            recommendations.append(f"{best_open} shows excellent engagement rates - consider using for high-value campaigns")
        
        # Volume distribution recommendations
        total_sent = sum(p['sent'] for p in provider_summary.values())
        for provider, stats in provider_summary.items():
            volume_percentage = stats['sent'] / total_sent * 100
            if volume_percentage > 70:
                recommendations.append(f"Consider diversifying email volume - {provider} handles {volume_percentage:.1f}% of traffic")
        
        return recommendations
