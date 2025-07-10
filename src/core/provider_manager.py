# src/core/provider_manager.py
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
class ProviderStats:
    """Statistics for an ESP provider"""
    name: str
    can_send: bool
    reputation_score: float
    daily_sent: int
    daily_limit: int
    hourly_sent: int
    hourly_limit: int
    last_success: Optional[datetime]
    last_failure: Optional[datetime]
    failure_count: int
    success_rate: float

class ProviderManager:
    """
    Manages ESP providers and their statistics
    Handles provider selection, reputation tracking, and failover logic
    """
    
    def __init__(self, db_session):
        self.db = db_session
        self.providers = {
            'sendgrid': {
                'name': 'SendGrid',
                'can_send': True,
                'reputation_score': 95.0,
                'daily_sent': 0,
                'daily_limit': 1500,
                'hourly_sent': 0,
                'hourly_limit': 100,
                'last_success': datetime.utcnow(),
                'last_failure': None,
                'failure_count': 0,
                'success_rate': 98.5
            },
            'amazon_ses': {
                'name': 'Amazon SES',
                'can_send': True,
                'reputation_score': 92.0,
                'daily_sent': 0,
                'daily_limit': 1000,
                'hourly_sent': 0,
                'hourly_limit': 80,
                'last_success': datetime.utcnow(),
                'last_failure': None,
                'failure_count': 0,
                'success_rate': 97.2
            },
            'postmark': {
                'name': 'Postmark',
                'can_send': True,
                'reputation_score': 89.0,
                'daily_sent': 0,
                'daily_limit': 500,
                'hourly_sent': 0,
                'hourly_limit': 50,
                'last_success': datetime.utcnow(),
                'last_failure': None,
                'failure_count': 0,
                'success_rate': 96.8
            }
        }
        
        # Reset counters daily
        self.last_reset = datetime.utcnow().date()
    
    def get_provider_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get current statistics for all providers"""
        self._reset_daily_counters_if_needed()
        
        stats = {}
        for provider_id, provider_data in self.providers.items():
            stats[provider_id] = {
                'name': provider_data['name'],
                'can_send': provider_data['can_send'],
                'reputation_score': provider_data['reputation_score'],
                'daily_sent': provider_data['daily_sent'],
                'daily_limit': provider_data['daily_limit'],
                'daily_remaining': provider_data['daily_limit'] - provider_data['daily_sent'],
                'hourly_sent': provider_data['hourly_sent'],
                'hourly_limit': provider_data['hourly_limit'],
                'hourly_remaining': provider_data['hourly_limit'] - provider_data['hourly_sent'],
                'success_rate': provider_data['success_rate'],
                'last_success': provider_data['last_success'],
                'last_failure': provider_data['last_failure'],
                'failure_count': provider_data['failure_count']
            }
        
        return stats
    
    def get_best_provider(self, email_count: int = 1) -> Optional[str]:
        """
        Get the best available provider for sending emails
        
        Args:
            email_count: Number of emails to send
            
        Returns:
            Provider ID or None if no provider available
        """
        self._reset_daily_counters_if_needed()
        
        available_providers = []
        
        for provider_id, provider_data in self.providers.items():
            if self._can_provider_send(provider_id, email_count):
                score = self._calculate_provider_score(provider_data)
                available_providers.append((provider_id, score))
        
        if not available_providers:
            logger.warning("No providers available for sending")
            return None
        
        # Sort by score (higher is better)
        available_providers.sort(key=lambda x: x[1], reverse=True)
        best_provider = available_providers[0][0]
        
        logger.info(f"Selected provider: {best_provider}")
        return best_provider
    
    def _can_provider_send(self, provider_id: str, email_count: int) -> bool:
        """Check if provider can send the specified number of emails"""
        provider = self.providers.get(provider_id)
        if not provider:
            return False
        
        return (
            provider['can_send'] and
            provider['reputation_score'] >= 70.0 and
            provider['daily_sent'] + email_count <= provider['daily_limit'] and
            provider['hourly_sent'] + email_count <= provider['hourly_limit'] and
            provider['failure_count'] < 10  # Circuit breaker
        )
    
    def _calculate_provider_score(self, provider_data: Dict) -> float:
        """Calculate provider score for selection"""
        base_score = provider_data['reputation_score']
        
        # Adjust for capacity
        daily_capacity = (provider_data['daily_limit'] - provider_data['daily_sent']) / provider_data['daily_limit']
        hourly_capacity = (provider_data['hourly_limit'] - provider_data['hourly_sent']) / provider_data['hourly_limit']
        
        capacity_score = min(daily_capacity, hourly_capacity) * 20  # Max 20 points
        
        # Adjust for recent failures
        failure_penalty = min(provider_data['failure_count'] * 5, 30)  # Max 30 point penalty
        
        # Adjust for success rate
        success_bonus = (provider_data['success_rate'] - 90) * 2  # Bonus for >90% success rate
        
        final_score = base_score + capacity_score - failure_penalty + success_bonus
        
        return max(0, final_score)
    
    def record_send_success(self, provider_id: str, email_count: int = 1):
        """Record successful send for provider"""
        provider = self.providers.get(provider_id)
        if not provider:
            return
        
        provider['daily_sent'] += email_count
        provider['hourly_sent'] += email_count
        provider['last_success'] = datetime.utcnow()
        provider['failure_count'] = max(0, provider['failure_count'] - 1)  # Reduce failure count
        
        # Update success rate (simple moving average)
        current_rate = provider['success_rate']
        provider['success_rate'] = min(100.0, current_rate + 0.1)
        
        logger.debug(f"Recorded success for {provider_id}: {email_count} emails")
    
    def record_send_failure(self, provider_id: str, error_details: str = ""):
        """Record failed send for provider"""
        provider = self.providers.get(provider_id)
        if not provider:
            return
        
        provider['last_failure'] = datetime.utcnow()
        provider['failure_count'] += 1
        
        # Update success rate
        current_rate = provider['success_rate']
        provider['success_rate'] = max(0.0, current_rate - 0.5)
        
        # Disable provider if too many failures
        if provider['failure_count'] >= 10:
            provider['can_send'] = False
            logger.warning(f"Disabled provider {provider_id} due to excessive failures")
        
        logger.warning(f"Recorded failure for {provider_id}: {error_details}")
    
    def update_provider_reputation(self, provider_id: str, new_reputation: float):
        """Update provider reputation score"""
        provider = self.providers.get(provider_id)
        if not provider:
            return
        
        old_reputation = provider['reputation_score']
        provider['reputation_score'] = max(0.0, min(100.0, new_reputation))
        
        logger.info(f"Updated {provider_id} reputation: {old_reputation} -> {new_reputation}")
    
    def enable_provider(self, provider_id: str):
        """Enable a disabled provider"""
        provider = self.providers.get(provider_id)
        if not provider:
            return
        
        provider['can_send'] = True
        provider['failure_count'] = 0
        logger.info(f"Enabled provider {provider_id}")
    
    def disable_provider(self, provider_id: str, reason: str = ""):
        """Disable a provider"""
        provider = self.providers.get(provider_id)
        if not provider:
            return
        
        provider['can_send'] = False
        logger.warning(f"Disabled provider {provider_id}: {reason}")
    
    def get_provider_health_check(self) -> Dict[str, Dict[str, Any]]:
        """Get health check status for all providers"""
        health_status = {}
        
        for provider_id, provider_data in self.providers.items():
            status = "healthy"
            issues = []
            
            # Check reputation
            if provider_data['reputation_score'] < 80:
                status = "degraded"
                issues.append(f"Low reputation: {provider_data['reputation_score']}")
            
            # Check failure rate
            if provider_data['failure_count'] > 5:
                status = "degraded"
                issues.append(f"High failure count: {provider_data['failure_count']}")
            
            # Check if disabled
            if not provider_data['can_send']:
                status = "unhealthy"
                issues.append("Provider disabled")
            
            # Check capacity
            daily_usage = (provider_data['daily_sent'] / provider_data['daily_limit']) * 100
            if daily_usage > 90:
                status = "degraded"
                issues.append(f"High daily usage: {daily_usage:.1f}%")
            
            health_status[provider_id] = {
                'status': status,
                'issues': issues,
                'reputation_score': provider_data['reputation_score'],
                'daily_usage_percent': daily_usage,
                'failure_count': provider_data['failure_count'],
                'last_success': provider_data['last_success'],
                'last_failure': provider_data['last_failure']
            }
        
        return health_status
    
    def _reset_daily_counters_if_needed(self):
        """Reset daily counters if it's a new day"""
        current_date = datetime.utcnow().date()
        
        if current_date > self.last_reset:
            logger.info("Resetting daily counters for all providers")
            
            for provider_data in self.providers.values():
                provider_data['daily_sent'] = 0
                
                # Re-enable providers that were disabled due to failures
                if not provider_data['can_send'] and provider_data['failure_count'] < 20:
                    provider_data['can_send'] = True
                    provider_data['failure_count'] = max(0, provider_data['failure_count'] - 5)
            
            self.last_reset = current_date
    
    def _reset_hourly_counters_if_needed(self):
        """Reset hourly counters if it's a new hour"""
        # This would be called by a background task every hour
        logger.info("Resetting hourly counters for all providers")
        
        for provider_data in self.providers.values():
            provider_data['hourly_sent'] = 0
    
    async def run_health_monitoring(self):
        """Background task to monitor provider health"""
        while True:
            try:
                # Check provider health
                health_status = self.get_provider_health_check()
                
                unhealthy_providers = [
                    provider_id for provider_id, status in health_status.items()
                    if status['status'] == 'unhealthy'
                ]
                
                if unhealthy_providers:
                    logger.warning(f"Unhealthy providers detected: {unhealthy_providers}")
                
                # Reset hourly counters
                current_minute = datetime.utcnow().minute
                if current_minute == 0:  # Top of the hour
                    self._reset_hourly_counters_if_needed()
                
                # Sleep for 5 minutes
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Error in health monitoring: {str(e)}")
                await asyncio.sleep(60)  # Shorter sleep on error
