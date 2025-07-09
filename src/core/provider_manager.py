# src/core/provider_manager.py
import sendgrid
import boto3
from postmarker.core import PostmarkClient
from typing import Dict, List, Optional, Tuple
import random
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from ..database.models import ProviderPerformance

@dataclass
class EmailProvider:
    name: str
    client: any
    weight: float
    daily_limit: int
    hourly_limit: int
    current_reputation: float
    priority: int
    dedicated_ip: Optional[str] = None
    features: Dict = None
    optimization: Dict = None
    current_daily_sent: int = 0
    current_hourly_sent: int = 0
    last_reset: datetime = None
    
    def __post_init__(self):
        if self.features is None:
            self.features = {}
        if self.optimization is None:
            self.optimization = {}
        if self.last_reset is None:
            self.last_reset = datetime.now()

class ProviderManager:
    def __init__(self, config_path: str = "config/providers.json", db_session: Session = None):
        self.db = db_session
        self.config = self._load_config(config_path)
        self.providers = self._initialize_providers()
        self.usage_tracker = {}
        self.last_rotation = datetime.now()
        self.global_settings = self.config.get('global_settings', {})
        
    def _load_config(self, config_path: str) -> Dict:
        """Load provider configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Replace environment variables
            config_str = json.dumps(config)
            for key, value in os.environ.items():
                config_str = config_str.replace(f"${{{key}}}", value)
            
            return json.loads(config_str)
        except Exception as e:
            print(f"Error loading provider config: {e}")
            return {}
    
    def _initialize_providers(self) -> List[EmailProvider]:
        """Initialize email service providers"""
        providers = []
        
        # SendGrid with dedicated IP
        if self.config.get('sendgrid', {}).get('api_key'):
            try:
                sg_config = self.config['sendgrid']
                sg_client = sendgrid.SendGridAPIClient(api_key=sg_config['api_key'])
                
                providers.append(EmailProvider(
                    name='sendgrid',
                    client=sg_client,
                    weight=sg_config.get('weight', 0.5),
                    daily_limit=sg_config.get('daily_limit', 10000),
                    hourly_limit=sg_config.get('hourly_limit', 1000),
                    current_reputation=sg_config.get('reputation_threshold', 0.85),
                    priority=sg_config.get('priority', 1),
                    dedicated_ip=sg_config.get('dedicated_ip'),
                    features=sg_config.get('features', {}),
                    optimization=sg_config.get('optimization', {})
                ))
                print("✓ SendGrid provider initialized")
            except Exception as e:
                print(f"✗ SendGrid initialization failed: {e}")
        
        # Amazon SES
        if self.config.get('aws_ses', {}).get('access_key'):
            try:
                ses_config = self.config['aws_ses']
                ses_client = boto3.client(
                    'ses',
                    region_name=ses_config.get('region', 'us-east-1'),
                    aws_access_key_id=ses_config['access_key'],
                    aws_secret_access_key=ses_config['secret_key']
                )
                
                providers.append(EmailProvider(
                    name='aws_ses',
                    client=ses_client,
                    weight=ses_config.get('weight', 0.3),
                    daily_limit=ses_config.get('daily_limit', 50000),
                    hourly_limit=ses_config.get('hourly_limit', 14),
                    current_reputation=ses_config.get('reputation_threshold', 0.80),
                    priority=ses_config.get('priority', 2),
                    features=ses_config.get('features', {}),
                    optimization=ses_config.get('optimization', {})
                ))
                print("✓ Amazon SES provider initialized")
            except Exception as e:
                print(f"✗ Amazon SES initialization failed: {e}")
        
        # Postmark for high-reputation sends
        if self.config.get('postmark', {}).get('server_token'):
            try:
                pm_config = self.config['postmark']
                pm_client = PostmarkClient(server_token=pm_config['server_token'])
                
                providers.append(EmailProvider(
                    name='postmark',
                    client=pm_client,
                    weight=pm_config.get('weight', 0.2),
                    daily_limit=pm_config.get('daily_limit', 10000),
                    hourly_limit=pm_config.get('hourly_limit', 500),
                    current_reputation=pm_config.get('reputation_threshold', 0.90),
                    priority=pm_config.get('priority', 3),
                    features=pm_config.get('features', {}),
                    optimization=pm_config.get('optimization', {})
                ))
                print("✓ Postmark provider initialized")
            except Exception as e:
                print(f"✗ Postmark initialization failed: {e}")
        
        return sorted(providers, key=lambda x: x.priority)
    
    def select_provider(self, recipient_email: str, engagement_score: float, 
                       campaign_data: Dict = None) -> Optional[EmailProvider]:
        """Intelligently select provider based on multiple factors"""
        
        if not self.providers:
            return None
        
        # Get domain from email
        domain = recipient_email.split('@')[-1].lower()
        
        # Check for domain-specific preferences
        domain_provider = self._get_domain_preferred_provider(domain)
        if domain_provider and self._can_provider_send(domain_provider):
            return domain_provider
        
        # High engagement users get best provider (highest reputation)
        if engagement_score > 0.8:
            best_provider = max(
                [p for p in self.providers if self._can_provider_send(p)],
                key=lambda p: p.current_reputation,
                default=None
            )
            if best_provider:
                return best_provider
        
        # Gmail/Google Workspace optimization
        if domain in ['gmail.com', 'googlemail.com'] or 'google' in domain:
            ses_provider = self._get_provider_by_name('aws_ses')
            if ses_provider and self._can_provider_send(ses_provider):
                return ses_provider
        
        # Microsoft domains optimization
        microsoft_domains = ['outlook.com', 'hotmail.com', 'live.com', 'msn.com']
        if any(ms_domain in domain for ms_domain in microsoft_domains):
            postmark_provider = self._get_provider_by_name('postmark')
            if postmark_provider and self._can_provider_send(postmark_provider):
                return postmark_provider
        
        # Weighted random selection based on reputation and capacity
        return self._weighted_random_selection()
    
    def _get_domain_preferred_provider(self, domain: str) -> Optional[EmailProvider]:
        """Get preferred provider for specific domain"""
        delivery_rules = self._load_delivery_rules()
        domain_rules = delivery_rules.get('domain_specific_rules', {})
        
        if domain in domain_rules:
            preferred = domain_rules[domain].get('preferred_provider')
            return self._get_provider_by_name(preferred)
        
        return None
    
    def _load_delivery_rules(self) -> Dict:
        """Load delivery rules configuration"""
        try:
            with open('config/delivery_rules.json', 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def _get_provider_by_name(self, name: str) -> Optional[EmailProvider]:
        """Get provider by name"""
        return next((p for p in self.providers if p.name == name), None)
    
    def _can_provider_send(self, provider: EmailProvider, count: int = 1) -> bool:
        """Check if provider can send specified number of emails"""
        # Reset counters if needed
        self._reset_counters_if_needed(provider)
        
        return (
            provider.current_daily_sent + count <= provider.daily_limit and
            provider.current_hourly_sent + count <= provider.hourly_limit and
            provider.current_reputation >= 0.7  # Minimum reputation threshold
        )
    
    def _weighted_random_selection(self) -> Optional[EmailProvider]:
        """Select provider based on weights and current performance"""
        available_providers = [p for p in self.providers if self._can_provider_send(p)]
        
        if not available_providers:
            return None
        
        # Calculate weights based on reputation and capacity
        total_weight = 0
        weighted_providers = []
        
        for provider in available_providers:
            # Weight based on reputation, capacity, and configured weight
            capacity_factor = (provider.daily_limit - provider.current_daily_sent) / provider.daily_limit
            weight = provider.weight * provider.current_reputation * capacity_factor
            
            total_weight += weight
            weighted_providers.append((provider, weight))
        
        if total_weight == 0:
            return available_providers[0]  # Fallback to first available
        
        # Random selection based on weights
        random_value = random.uniform(0, total_weight)
        cumulative_weight = 0
        
        for provider, weight in weighted_providers:
            cumulative_weight += weight
            if random_value <= cumulative_weight:
                return provider
        
        return available_providers[0]  # Fallback
    
    def _reset_counters_if_needed(self, provider: EmailProvider):
        """Reset hourly/daily counters if time periods have passed"""
        now = datetime.now()
        
        # Reset hourly counter
        if (now - provider.last_reset).total_seconds() >= 3600:
            provider.current_hourly_sent = 0
        
        # Reset daily counter
        if (now - provider.last_reset).days >= 1:
            provider.current_daily_sent = 0
            provider.current_hourly_sent = 0
            provider.last_reset = now
    
    def update_provider_usage(self, provider_name: str, count: int = 1):
        """Update provider usage counters"""
        provider = self._get_provider_by_name(provider_name)
        if provider:
            provider.current_daily_sent += count
            provider.current_hourly_sent += count
    
    def update_reputation(self, provider_name: str, event_type: str, 
                         campaign_id: int = None):
        """Update provider reputation based on events"""
        provider = self._get_provider_by_name(provider_name)
        if not provider:
            return
        
        # Reputation change values
        reputation_changes = {
            'delivered': 0.001,
            'opened': 0.002,
            'clicked': 0.003,
            'soft_bounce': -0.005,
            'hard_bounce': -0.01,
            'complaint': -0.02,
            'blocked': -0.03,
            'timeout': -0.005,
            'rejected': -0.015
        }
        
        change = reputation_changes.get(event_type, 0)
        old_reputation = provider.current_reputation
        provider.current_reputation = max(0.1, min(1.0, provider.current_reputation + change))
        
        # Log significant reputation changes
        if abs(change) > 0.01:
            print(f"Provider {provider_name} reputation: {old_reputation:.3f} → {provider.current_reputation:.3f} ({event_type})")
        
        # Store in database if available
        if self.db:
            self._store_performance_data(provider_name, event_type, campaign_id)
    
    def _store_performance_data(self, provider_name: str, event_type: str, 
                               campaign_id: int = None):
        """Store performance data in database"""
        try:
            today = datetime.now().date()
            
            # Get or create performance record for today
            perf = self.db.query(ProviderPerformance).filter_by(
                provider_name=provider_name,
                date=today
            ).first()
            
            if not perf:
                perf = ProviderPerformance(
                    provider_name=provider_name,
                    date=today
                )
                self.db.add(perf)
            
            # Update metrics based on event type
            if event_type == 'delivered':
                perf.emails_delivered += 1
            elif event_type in ['hard_bounce', 'soft_bounce']:
                perf.emails_bounced += 1
            elif event_type == 'complaint':
                perf.emails_complained += 1
            
            # Update rates
            if perf.emails_sent > 0:
                perf.delivery_rate = perf.emails_delivered / perf.emails_sent
                perf.bounce_rate = perf.emails_bounced / perf.emails_sent
                perf.complaint_rate = perf.emails_complained / perf.emails_sent
            
            # Update reputation score
            provider = self._get_provider_by_name(provider_name)
            if provider:
                perf.reputation_score = provider.current_reputation
            
            self.db.commit()
            
        except Exception as e:
            print(f"Error storing performance data: {e}")
            if self.db:
                self.db.rollback()
    
    def get_provider_stats(self) -> Dict:
        """Get current provider statistics"""
        stats = {}
        
        for provider in self.providers:
            stats[provider.name] = {
                'reputation': provider.current_reputation,
                'daily_sent': provider.current_daily_sent,
                'daily_limit': provider.daily_limit,
                'hourly_sent': provider.current_hourly_sent,
                'hourly_limit': provider.hourly_limit,
                'capacity_remaining': provider.daily_limit - provider.current_daily_sent,
                'can_send': self._can_provider_send(provider),
                'priority': provider.priority,
                'weight': provider.weight
            }
        
        return stats
    
    def get_best_send_time(self, recipient_email: str, time_zone: str = 'US/Eastern') -> datetime:
        """Get optimal send time for recipient"""
        delivery_rules = self._load_delivery_rules()
        time_optimization = delivery_rules.get('send_time_optimization', {})
        
        if not time_optimization.get('enabled', False):
            return datetime.now()
        
        # Get time zone specific optimal hours
        tz_settings = time_optimization.get('time_zones', {}).get(time_zone, {})
        optimal_hours = tz_settings.get('optimal_hours', [9, 10, 14, 15])
        
        # Get current time and find next optimal hour
        now = datetime.now()
        for hour in optimal_hours:
            send_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if send_time > now:
                return send_time
        
        # If no optimal time today, use first optimal hour tomorrow
        tomorrow = now.replace(hour=optimal_hours[0], minute=0, second=0, microsecond=0)
        tomorrow += timedelta(days=1)
        return tomorrow
