# src/core/warming_system.py
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import json
from sqlalchemy.orm import Session
from ..database.models import WarmingProgress, Subscriber

class IPWarmingSchedule:
    def __init__(self, config_path: str = "config/warming_schedule.json", 
                 target_volume: int = 3000, profile: str = "standard"):
        self.config = self._load_config(config_path)
        self.target_volume = target_volume
        self.profile = profile
        self.schedule = self._generate_warming_schedule()
        self.current_day = 1
        self.start_date = datetime.now().date()
        
    def _load_config(self, config_path: str) -> Dict:
        """Load warming configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading warming config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Get default warming configuration"""
        return {
            "active_profile": "standard",
            "schedule": {
                "week_1": {"days": []},
                "week_2": {"days": []},
                "week_3": {"days": []},
                "week_4_plus": {"default": {}}
            }
        }
    
    def _generate_warming_schedule(self) -> List[Dict]:
        """Generate warming schedule based on configuration"""
        schedule = []
        config_schedule = self.config.get('schedule', {})
        
        # Week 1: Most engaged subscribers only
        week1_days = config_schedule.get('week_1', {}).get('days', [])
        schedule.extend(week1_days)
        
        # Week 2: Expand to engaged subscribers
        week2_days = config_schedule.get('week_2', {}).get('days', [])
        schedule.extend(week2_days)
        
        # Week 3: Approaching target volume
        week3_days = config_schedule.get('week_3', {}).get('days', [])
        schedule.extend(week3_days)
        
        # Week 4+: Full volume
        week4_default = config_schedule.get('week_4_plus', {}).get('default', {})
        if week4_default:
            for day in range(22, 46):  # Extend to 45 days
                day_config = week4_default.copy()
                day_config['day'] = day
                schedule.append(day_config)
        
        return schedule
    
    def get_current_day_config(self, warming_day: int = None) -> Dict:
        """Get configuration for current warming day"""
        if warming_day is None:
            warming_day = self.current_day
        
        if warming_day <= len(self.schedule):
            return self.schedule[warming_day - 1]
        
        # After warming period, use full capacity
        return {
            'day': warming_day,
            'volume': self.target_volume,
            'segment': 'all_active',
            'hourly_limit': 600,
            'engagement_threshold': 0.0,
            'warming_complete': True
        }
    
    def get_segment_criteria(self, segment_name: str) -> Dict:
        """Get SQL criteria for segment selection during warming"""
        segments = self.config.get('segment_definitions', {})
        
        default_segments = {
            'most_engaged': {
                'min_engagement_score': 0.9,
                'min_opens_last_30_days': 10,
                'max_days_since_last_open': 7,
                'min_clicks_last_30_days': 3,
                'exclude_bounces': True,
                'exclude_complaints': True
            },
            'highly_engaged': {
                'min_engagement_score': 0.7,
                'min_opens_last_30_days': 5,
                'max_days_since_last_open': 14,
                'min_clicks_last_30_days': 1,
                'exclude_bounces': True,
                'exclude_complaints': True
            },
            'engaged': {
                'min_engagement_score': 0.5,
                'min_opens_last_30_days': 2,
                'max_days_since_last_open': 30,
                'exclude_bounces': True,
                'exclude_complaints': True
            },
            'moderately_engaged': {
                'min_engagement_score': 0.3,
                'min_opens_last_30_days': 1,
                'max_days_since_last_open': 60,
                'exclude_bounces': True,
                'exclude_complaints': True
            },
            'all_active': {
                'min_engagement_score': 0.0,
                'max_days_since_last_open': 180,
                'exclude_bounces': True,
                'exclude_complaints': True,
                'status': 'active'
            }
        }
        
        return segments.get(segment_name, default_segments.get(segment_name, default_segments['all_active']))
    
    def get_subscribers_for_warming(self, db_session: Session, 
                                   warming_day: int = None) -> List[Dict]:
        """Get subscribers for current warming day"""
        day_config = self.get_current_day_config(warming_day)
        segment_name = day_config.get('segment', 'all_active')
        volume = day_config.get('volume', 100)
        
        # Get segment criteria
        criteria = self.get_segment_criteria(segment_name)
        
        # Build query
        query = db_session.query(Subscriber).filter(Subscriber.status == 'active')
        
        # Apply engagement score filter
        if 'min_engagement_score' in criteria:
            query = query.filter(Subscriber.engagement_score >= criteria['min_engagement_score'])
        
        # Apply last open filter
        if 'max_days_since_last_open' in criteria:
            cutoff_date = datetime.now() - timedelta(days=criteria['max_days_since_last_open'])
            query = query.filter(Subscriber.last_open >= cutoff_date)
        
        # Exclude bounces and complaints
        if criteria.get('exclude_bounces', True):
            query = query.filter(Subscriber.bounce_count == 0)
        
        if criteria.get('exclude_complaints', True):
            query = query.filter(Subscriber.complaint_count == 0)
        
        # Order by engagement score (highest first) and limit
        subscribers = query.order_by(Subscriber.engagement_score.desc()).limit(volume).all()
        
        return [
            {
                'id': sub.id,
                'email': sub.email,
                'name': sub.name,
                'engagement_score': sub.engagement_score,
                'last_open': sub.last_open,
                'segment': segment_name
            }
            for sub in subscribers
        ]
    
    def should_pause_warming(self, performance_metrics: Dict) -> Tuple[bool, str]:
        """Check if warming should be paused based on performance"""
        monitoring_config = self.config.get('monitoring', {})
        pause_actions = monitoring_config.get('actions', {}).get('pause_warming', {})
        
        # Check bounce rate
        if performance_metrics.get('bounce_rate', 0) > pause_actions.get('bounce_rate_above', 0.10):
            return True, f"High bounce rate: {performance_metrics['bounce_rate']:.3f}"
        
        # Check complaint rate
        if performance_metrics.get('complaint_rate', 0) > pause_actions.get('complaint_rate_above', 0.003):
            return True, f"High complaint rate: {performance_metrics['complaint_rate']:.3f}"
        
        # Check delivery rate
        if performance_metrics.get('delivery_rate', 1.0) < pause_actions.get('delivery_rate_below', 0.85):
            return True, f"Low delivery rate: {performance_metrics['delivery_rate']:.3f}"
        
        return False, ""
    
    def should_reduce_volume(self, performance_metrics: Dict) -> Tuple[bool, str, float]:
        """Check if volume should be reduced and by how much"""
        monitoring_config = self.config.get('monitoring', {})
        reduce_actions = monitoring_config.get('actions', {}).get('reduce_volume', {})
        
        reduction_factor = 1.0
        reason = ""
        
        # Check bounce rate
        if performance_metrics.get('bounce_rate', 0) > reduce_actions.get('bounce_rate_above', 0.08):
            reduction_factor = 0.5
            reason = f"High bounce rate: {performance_metrics['bounce_rate']:.3f}"
        
        # Check complaint rate
        elif performance_metrics.get('complaint_rate', 0) > reduce_actions.get('complaint_rate_above', 0.002):
            reduction_factor = 0.7
            reason = f"High complaint rate: {performance_metrics['complaint_rate']:.3f}"
        
        # Check delivery rate
        elif performance_metrics.get('delivery_rate', 1.0) < reduce_actions.get('delivery_rate_below', 0.90):
            reduction_factor = 0.8
            reason = f"Low delivery rate: {performance_metrics['delivery_rate']:.3f}"
        
        return reduction_factor < 1.0, reason, reduction_factor
    
    def update_warming_progress(self, db_session: Session, provider_name: str, 
                               warming_day: int, actual_volume: int, 
                               performance_metrics: Dict):
        """Update warming progress in database"""
        try:
            today = datetime.now().date()
            day_config = self.get_current_day_config(warming_day)
            
            # Get or create progress record
            progress = db_session.query(WarmingProgress).filter_by(
                provider_name=provider_name,
                warming_day=warming_day,
                date=today
            ).first()
            
            if not progress:
                progress = WarmingProgress(
                    provider_name=provider_name,
                    warming_day=warming_day,
                    date=today,
                    planned_volume=day_config.get('volume', 0),
                    planned_segment=day_config.get('segment', 'unknown')
                )
                db_session.add(progress)
            
            # Update metrics
            progress.actual_volume = actual_volume
            progress.delivery_rate = performance_metrics.get('delivery_rate', 0.0)
            progress.open_rate = performance_metrics.get('open_rate', 0.0)
            progress.click_rate = performance_metrics.get('click_rate', 0.0)
            progress.bounce_rate = performance_metrics.get('bounce_rate', 0.0)
            progress.complaint_rate = performance_metrics.get('complaint_rate', 0.0)
            
            # Check if warming should be paused or volume reduced
            should_pause, pause_reason = self.should_pause_warming(performance_metrics)
            should_reduce, reduce_reason, reduction_factor = self.should_reduce_volume(performance_metrics)
            
            if should_pause:
                progress.status = 'paused'
                progress.notes = f"Paused: {pause_reason}"
            elif should_reduce:
                progress.status = 'reduced'
                progress.notes = f"Volume reduced by {(1-reduction_factor)*100:.0f}%: {reduce_reason}"
            else:
                progress.status = 'active'
                progress.notes = "On track"
            
            progress.updated_at = datetime.now()
            db_session.commit()
            
            return progress.status, progress.notes
            
        except Exception as e:
            print(f"Error updating warming progress: {e}")
            db_session.rollback()
            return 'error', str(e)
    
    def get_warming_status(self, db_session: Session, provider_name: str) -> Dict:
        """Get current warming status for provider"""
        try:
            # Get recent progress records
            recent_progress = db_session.query(WarmingProgress).filter_by(
                provider_name=provider_name
            ).order_by(WarmingProgress.warming_day.desc()).limit(7).all()
            
            if not recent_progress:
                return {
                    'status': 'not_started',
                    'current_day': 1,
                    'progress_percentage': 0,
                    'recent_performance': {}
                }
            
            latest = recent_progress[0]
            
            # Calculate progress percentage
            total_days = len(self.schedule)
            progress_percentage = (latest.warming_day / total_days) * 100
            
            # Calculate average performance over last 7 days
            avg_performance = {
                'delivery_rate': sum(p.delivery_rate for p in recent_progress) / len(recent_progress),
                'open_rate': sum(p.open_rate for p in recent_progress) / len(recent_progress),
                'bounce_rate': sum(p.bounce_rate for p in recent_progress) / len(recent_progress),
                'complaint_rate': sum(p.complaint_rate for p in recent_progress) / len(recent_progress)
            }
            
            return {
                'status': latest.status,
                'current_day': latest.warming_day,
                'progress_percentage': min(100, progress_percentage),
                'recent_performance': avg_performance,
                'last_update': latest.updated_at,
                'notes': latest.notes,
                'warming_complete': latest.warming_day >= total_days
            }
            
        except Exception as e:
            print(f"Error getting warming status: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def advance_warming_day(self):
        """Advance to next warming day"""
        self.current_day += 1
        return self.current_day
    
    def is_warming_complete(self) -> bool:
        """Check if warming period is complete"""
        return self.current_day > len(self.schedule)
    
    def get_recommended_next_volume(self, current_performance: Dict) -> int:
        """Get recommended volume for next day based on current performance"""
        day_config = self.get_current_day_config(self.current_day + 1)
        base_volume = day_config.get('volume', self.target_volume)
        
        # Adjust based on performance
        should_reduce, _, reduction_factor = self.should_reduce_volume(current_performance)
        
        if should_reduce:
            return int(base_volume * reduction_factor)
        
        # If performance is excellent, allow slight increase
        if (current_performance.get('delivery_rate', 0) > 0.98 and
            current_performance.get('bounce_rate', 1) < 0.02 and
            current_performance.get('complaint_rate', 1) < 0.001):
            return min(self.target_volume, int(base_volume * 1.1))
        
        return base_volume
