# src/core/warming_system.py
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class WarmingSchedule:
    """IP warming schedule configuration"""
    day: int
    max_emails: int
    recommended_emails: int
    esp_limits: Dict[str, int]
    notes: str

class IPWarmingSchedule:
    """
    IP Warming System for gradual reputation building
    Manages sending limits during IP warming period
    """
    
    def __init__(self):
        # Standard IP warming schedule (30-day plan)
        self.warming_schedule = {
            1: WarmingSchedule(1, 50, 25, {'sendgrid': 20, 'amazon_ses': 15, 'postmark': 10}, "Start slow, monitor closely"),
            2: WarmingSchedule(2, 100, 75, {'sendgrid': 40, 'amazon_ses': 30, 'postmark': 20}, "Gradual increase"),
            3: WarmingSchedule(3, 200, 150, {'sendgrid': 80, 'amazon_ses': 60, 'postmark': 40}, "Monitor engagement"),
            4: WarmingSchedule(4, 400, 300, {'sendgrid': 160, 'amazon_ses': 120, 'postmark': 80}, "Check reputation"),
            5: WarmingSchedule(5, 600, 500, {'sendgrid': 240, 'amazon_ses': 180, 'postmark': 120}, "Steady growth"),
            7: WarmingSchedule(7, 1000, 800, {'sendgrid': 400, 'amazon_ses': 300, 'postmark': 200}, "Week 1 complete"),
            10: WarmingSchedule(10, 1500, 1200, {'sendgrid': 600, 'amazon_ses': 450, 'postmark': 300}, "Increase volume"),
            14: WarmingSchedule(14, 2500, 2000, {'sendgrid': 1000, 'amazon_ses': 750, 'postmark': 500}, "Week 2 complete"),
            21: WarmingSchedule(21, 5000, 4000, {'sendgrid': 2000, 'amazon_ses': 1500, 'postmark': 1000}, "Week 3 complete"),
            30: WarmingSchedule(30, 10000, 8000, {'sendgrid': 4000, 'amazon_ses': 3000, 'postmark': 2000}, "Warming complete")
        }
        
        # Track warming status for each provider
        self.warming_status = {}
    
    def get_warming_status(self, db_session, provider: str) -> Dict[str, Any]:
        """Get current warming status for provider"""
        try:
            # In production, this would query the database
            # For now, return mock data
            
            warming_start_date = datetime.utcnow() - timedelta(days=7)  # Mock: started 7 days ago
            current_day = (datetime.utcnow() - warming_start_date).days + 1
            
            # Get current schedule
            schedule = self._get_schedule_for_day(current_day)
            
            return {
                'provider': provider,
                'status': 'active' if current_day <= 30 else 'completed',
                'warming_day': current_day,
                'start_date': warming_start_date.isoformat(),
                'current_limits': schedule.esp_limits.get(provider, 0) if schedule else 0,
                'max_daily_emails': schedule.max_emails if schedule else 10000,
                'recommended_daily_emails': schedule.recommended_emails if schedule else 8000,
                'notes': schedule.notes if schedule else "Warming completed",
                'next_milestone': self._get_next_milestone(current_day),
                'completion_percentage': min(100, (current_day / 30) * 100)
            }
        except Exception as e:
            logger.error(f"Error getting warming status for {provider}: {str(e)}")
            return {
                'provider': provider,
                'status': 'error',
                'error': str(e)
            }
    
    def _get_schedule_for_day(self, day: int) -> Optional[WarmingSchedule]:
        """Get warming schedule for specific day"""
        # Find the appropriate schedule (use the highest day <= current day)
        applicable_days = [d for d in self.warming_schedule.keys() if d <= day]
        
        if not applicable_days:
            return self.warming_schedule[1]  # Default to day 1
        
        latest_day = max(applicable_days)
        return self.warming_schedule[latest_day]
    
    def _get_next_milestone(self, current_day: int) -> Optional[Dict[str, Any]]:
        """Get next warming milestone"""
        future_days = [d for d in self.warming_schedule.keys() if d > current_day]
        
        if not future_days:
            return None
        
        next_day = min(future_days)
        next_schedule = self.warming_schedule[next_day]
        
        return {
            'day': next_day,
            'days_remaining': next_day - current_day,
            'max_emails': next_schedule.max_emails,
            'notes': next_schedule.notes
        }
    
    def get_daily_sending_limit(self, provider: str, warming_day: int) -> int:
        """Get daily sending limit for provider on specific warming day"""
        schedule = self._get_schedule_for_day(warming_day)
        
        if not schedule:
            return 0
        
        return schedule.esp_limits.get(provider, 0)
    
    def is_warming_active(self, provider: str) -> bool:
        """Check if IP warming is active for provider"""
        status = self.warming_status.get(provider, {})
        return status.get('status') == 'active'
    
    def start_warming_schedule(self, provider: str, db_session) -> Dict[str, Any]:
        """Start IP warming schedule for provider"""
        try:
            start_date = datetime.utcnow()
            
            # In production, this would be stored in database
            self.warming_status[provider] = {
                'status': 'active',
                'start_date': start_date,
                'current_day': 1,
                'daily_sent': 0,
                'total_sent': 0
            }
            
            logger.info(f"Started IP warming schedule for {provider}")
            
            return {
                'success': True,
                'provider': provider,
                'start_date': start_date.isoformat(),
                'initial_limit': self.warming_schedule[1].esp_limits.get(provider, 0),
                'schedule_duration': '30 days',
                'message': f'IP warming started for {provider}'
            }
            
        except Exception as e:
            logger.error(f"Error starting warming schedule for {provider}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def pause_warming_schedule(self, provider: str, reason: str = "") -> Dict[str, Any]:
        """Pause IP warming schedule"""
        try:
            if provider in self.warming_status:
                self.warming_status[provider]['status'] = 'paused'
                self.warming_status[provider]['pause_reason'] = reason
                self.warming_status[provider]['paused_at'] = datetime.utcnow()
            
            logger.warning(f"Paused IP warming for {provider}: {reason}")
            
            return {
                'success': True,
                'provider': provider,
                'status': 'paused',
                'reason': reason,
                'message': f'IP warming paused for {provider}'
            }
            
        except Exception as e:
            logger.error(f"Error pausing warming schedule for {provider}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def resume_warming_schedule(self, provider: str) -> Dict[str, Any]:
        """Resume paused IP warming schedule"""
        try:
            if provider in self.warming_status:
                self.warming_status[provider]['status'] = 'active'
                self.warming_status[provider]['resumed_at'] = datetime.utcnow()
                if 'pause_reason' in self.warming_status[provider]:
                    del self.warming_status[provider]['pause_reason']
            
            logger.info(f"Resumed IP warming for {provider}")
            
            return {
                'success': True,
                'provider': provider,
                'status': 'active',
                'message': f'IP warming resumed for {provider}'
            }
            
        except Exception as e:
            logger.error(f"Error resuming warming schedule for {provider}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def record_warming_send(self, provider: str, email_count: int) -> bool:
        """Record emails sent during warming period"""
        try:
            if provider not in self.warming_status:
                return False
            
            status = self.warming_status[provider]
            
            # Calculate current warming day
            start_date = status['start_date']
            current_day = (datetime.utcnow() - start_date).days + 1
            
            # Get daily limit
            daily_limit = self.get_daily_sending_limit(provider, current_day)
            
            # Check if sending would exceed limit
            current_daily_sent = status.get('daily_sent', 0)
            if current_daily_sent + email_count > daily_limit:
                logger.warning(f"Warming limit exceeded for {provider}: {current_daily_sent + email_count} > {daily_limit}")
                return False
            
            # Record the send
            status['daily_sent'] = current_daily_sent + email_count
            status['total_sent'] = status.get('total_sent', 0) + email_count
            status['current_day'] = current_day
            status['last_send'] = datetime.utcnow()
            
            logger.debug(f"Recorded warming send for {provider}: {email_count} emails (day {current_day})")
            return True
            
        except Exception as e:
            logger.error(f"Error recording warming send for {provider}: {str(e)}")
            return False
    
    def get_warming_recommendations(self, provider: str) -> List[str]:
        """Get warming recommendations for provider"""
        recommendations = []
        
        try:
            if provider not in self.warming_status:
                recommendations.append("Start IP warming schedule")
                return recommendations
            
            status = self.warming_status[provider]
            current_day = status.get('current_day', 1)
            daily_sent = status.get('daily_sent', 0)
            
            # Get current schedule
            schedule = self._get_schedule_for_day(current_day)
            if not schedule:
                return recommendations
            
            daily_limit = schedule.esp_limits.get(provider, 0)
            
            # Usage recommendations
            usage_percentage = (daily_sent / daily_limit * 100) if daily_limit > 0 else 0
            
            if usage_percentage < 50:
                recommendations.append(f"Consider increasing daily volume (currently {usage_percentage:.1f}% of limit)")
            elif usage_percentage > 90:
                recommendations.append("Approaching daily limit - monitor engagement closely")
            
            # Engagement recommendations
            if current_day <= 7:
                recommendations.append("Focus on highly engaged subscribers only")
                recommendations.append("Monitor bounce and complaint rates closely")
            elif current_day <= 14:
                recommendations.append("Gradually expand to broader audience")
                recommendations.append("Maintain consistent sending schedule")
            elif current_day <= 21:
                recommendations.append("Continue monitoring reputation metrics")
                recommendations.append("Consider A/B testing content")
            else:
                recommendations.append("Warming nearly complete - prepare for full volume")
            
            # Schedule-specific notes
            if schedule.notes:
                recommendations.append(f"Day {current_day} focus: {schedule.notes}")
            
        except Exception as e:
            logger.error(f"Error getting warming recommendations for {provider}: {str(e)}")
            recommendations.append("Error getting recommendations - check warming status")
        
        return recommendations
    
    def get_warming_analytics(self, provider: str) -> Dict[str, Any]:
        """Get warming analytics and progress"""
        try:
            if provider not in self.warming_status:
                return {'error': 'No warming data available'}
            
            status = self.warming_status[provider]
            current_day = status.get('current_day', 1)
            
            # Calculate progress metrics
            total_sent = status.get('total_sent', 0)
            daily_sent = status.get('daily_sent', 0)
            
            # Get schedule progression
            schedule_progression = []
            for day in sorted(self.warming_schedule.keys()):
                if day <= current_day:
                    schedule = self.warming_schedule[day]
                    schedule_progression.append({
                        'day': day,
                        'limit': schedule.esp_limits.get(provider, 0),
                        'status': 'completed' if day < current_day else 'current'
                    })
            
            return {
                'provider': provider,
                'current_day': current_day,
                'total_sent': total_sent,
                'daily_sent': daily_sent,
                'completion_percentage': min(100, (current_day / 30) * 100),
                'schedule_progression': schedule_progression,
                'status': status.get('status', 'unknown'),
                'start_date': status.get('start_date', datetime.utcnow()).isoformat(),
                'recommendations': self.get_warming_recommendations(provider)
            }
            
        except Exception as e:
            logger.error(f"Error getting warming analytics for {provider}: {str(e)}")
            return {'error': str(e)}
