# config/esp_config.py
import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

class ESPProvider(Enum):
    SENDGRID = "sendgrid"
    AMAZON_SES = "amazon_ses"
    POSTMARK = "postmark"

class ESPStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    WARMING = "warming"
    SUSPENDED = "suspended"

@dataclass
class ESPConfig:
    provider: ESPProvider
    api_key: str
    from_email: str
    from_name: str
    daily_limit: int
    hourly_limit: int
    batch_size: int
    delay_between_batches: float
    status: ESPStatus
    priority: int  # Lower number = higher priority
    reputation_score: float = 100.0
    current_daily_sent: int = 0
    current_hourly_sent: int = 0
    last_reset_time: Optional[str] = None
    
    def can_send(self, count: int = 1) -> bool:
        """Check if ESP can send specified number of emails"""
        return (
            self.status == ESPStatus.ACTIVE and
            self.current_daily_sent + count <= self.daily_limit and
            self.current_hourly_sent + count <= self.hourly_limit and
            self.reputation_score >= 70.0
        )

class ESPConfigManager:
    def __init__(self):
        self.configs = self._load_esp_configs()
    
    def _load_esp_configs(self) -> Dict[ESPProvider, ESPConfig]:
        """Load ESP configurations from environment variables"""
        configs = {}
        
        # SendGrid Configuration
        if os.getenv('SENDGRID_API_KEY'):
            configs[ESPProvider.SENDGRID] = ESPConfig(
                provider=ESPProvider.SENDGRID,
                api_key=os.getenv('SENDGRID_API_KEY'),
                from_email=os.getenv('SENDGRID_FROM_EMAIL', 'chris@mail.cjsinsurancesolutions.com'),
                from_name=os.getenv('FROM_NAME', 'Chris - CJS Insurance Solutions'),
                daily_limit=int(os.getenv('SENDGRID_DAILY_LIMIT', '1500')),
                hourly_limit=int(os.getenv('SENDGRID_HOURLY_LIMIT', '100')),
                batch_size=int(os.getenv('SENDGRID_BATCH_SIZE', '50')),
                delay_between_batches=float(os.getenv('SENDGRID_DELAY', '2.0')),
                status=ESPStatus.ACTIVE,
                priority=1
            )
        
        # Amazon SES Configuration
        if os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY'):
            configs[ESPProvider.AMAZON_SES] = ESPConfig(
                provider=ESPProvider.AMAZON_SES,
                api_key=os.getenv('AWS_ACCESS_KEY_ID'),
                from_email=os.getenv('SES_FROM_EMAIL', 'chris@mail.cjsinsurancesolutions.com'),
                from_name=os.getenv('FROM_NAME', 'Chris - CJS Insurance Solutions'),
                daily_limit=int(os.getenv('SES_DAILY_LIMIT', '1000')),
                hourly_limit=int(os.getenv('SES_HOURLY_LIMIT', '80')),
                batch_size=int(os.getenv('SES_BATCH_SIZE', '40')),
                delay_between_batches=float(os.getenv('SES_DELAY', '3.0')),
                status=ESPStatus.ACTIVE,
                priority=2
            )
        
        # Postmark Configuration
        if os.getenv('POSTMARK_API_KEY'):
            configs[ESPProvider.POSTMARK] = ESPConfig(
                provider=ESPProvider.POSTMARK,
                api_key=os.getenv('POSTMARK_API_KEY'),
                from_email=os.getenv('POSTMARK_FROM_EMAIL', 'chris@mail.cjsinsurancesolutions.com'),
                from_name=os.getenv('FROM_NAME', 'Chris - CJS Insurance Solutions'),
                daily_limit=int(os.getenv('POSTMARK_DAILY_LIMIT', '500')),
                hourly_limit=int(os.getenv('POSTMARK_HOURLY_LIMIT', '50')),
                batch_size=int(os.getenv('POSTMARK_BATCH_SIZE', '25')),
                delay_between_batches=float(os.getenv('POSTMARK_DELAY', '4.0')),
                status=ESPStatus.ACTIVE,
                priority=3
            )
        
        return configs
    
    def get_available_esps(self) -> List[ESPConfig]:
        """Get list of available ESPs sorted by priority"""
        available = [
            config for config in self.configs.values()
            if config.status == ESPStatus.ACTIVE
        ]
        return sorted(available, key=lambda x: x.priority)
    
    def get_best_esp_for_sending(self, count: int = 1) -> Optional[ESPConfig]:
        """Get the best ESP for sending specified number of emails"""
        for esp_config in self.get_available_esps():
            if esp_config.can_send(count):
                return esp_config
        return None
    
    def update_sent_count(self, provider: ESPProvider, count: int):
        """Update sent count for an ESP"""
        if provider in self.configs:
            self.configs[provider].current_daily_sent += count
            self.configs[provider].current_hourly_sent += count
    
    def update_reputation_score(self, provider: ESPProvider, score: float):
        """Update reputation score for an ESP"""
        if provider in self.configs:
            self.configs[provider].reputation_score = score
    
    def reset_hourly_limits(self):
        """Reset hourly limits for all ESPs"""
        for config in self.configs.values():
            config.current_hourly_sent = 0
    
    def reset_daily_limits(self):
        """Reset daily limits for all ESPs"""
        for config in self.configs.values():
            config.current_daily_sent = 0
            config.current_hourly_sent = 0
