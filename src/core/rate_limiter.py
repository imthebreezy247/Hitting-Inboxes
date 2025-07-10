# src/core/rate_limiter.py
import asyncio
import time
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RateLimitType(Enum):
    """Types of rate limits"""
    HOURLY = "hourly"
    DAILY = "daily"
    BURST = "burst"
    DOMAIN = "domain"

@dataclass
class RateLimit:
    """Rate limit configuration"""
    limit: int
    window_seconds: int
    burst_limit: Optional[int] = None

class TokenBucket:
    """
    Token bucket algorithm implementation for rate limiting
    Allows burst traffic up to bucket capacity while maintaining average rate
    """
    
    def __init__(self, rate: float, capacity: int):
        """
        Initialize token bucket
        
        Args:
            rate: Tokens per second refill rate
            capacity: Maximum bucket capacity
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from bucket
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if not enough tokens
        """
        async with self._lock:
            now = time.time()
            
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    async def wait_for_tokens(self, tokens: int = 1, max_wait: float = 60.0) -> bool:
        """
        Wait for tokens to become available
        
        Args:
            tokens: Number of tokens needed
            max_wait: Maximum time to wait in seconds
            
        Returns:
            True if tokens were obtained, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            if await self.consume(tokens):
                return True
            
            # Calculate wait time until next token
            wait_time = min(1.0, tokens / self.rate)
            await asyncio.sleep(wait_time)
        
        return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current bucket status"""
        now = time.time()
        elapsed = now - self.last_update
        current_tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        
        return {
            'current_tokens': current_tokens,
            'capacity': self.capacity,
            'rate': self.rate,
            'utilization_percent': ((self.capacity - current_tokens) / self.capacity) * 100
        }

class DomainThrottler:
    """
    Domain-specific throttling to prevent overwhelming specific email domains
    """
    
    def __init__(self):
        self.domain_buckets = {}
        self.domain_limits = {
            'gmail.com': TokenBucket(rate=10.0, capacity=50),      # 10/sec, burst 50
            'googlemail.com': TokenBucket(rate=10.0, capacity=50),
            'outlook.com': TokenBucket(rate=8.0, capacity=40),     # 8/sec, burst 40
            'hotmail.com': TokenBucket(rate=8.0, capacity=40),
            'live.com': TokenBucket(rate=8.0, capacity=40),
            'yahoo.com': TokenBucket(rate=5.0, capacity=25),       # 5/sec, burst 25
            'aol.com': TokenBucket(rate=3.0, capacity=15),         # 3/sec, burst 15
            'icloud.com': TokenBucket(rate=5.0, capacity=25),
            'me.com': TokenBucket(rate=5.0, capacity=25),
            'mac.com': TokenBucket(rate=5.0, capacity=25),
            'default': TokenBucket(rate=15.0, capacity=75)         # Default for other domains
        }
    
    async def can_send_to_domain(self, domain: str, count: int = 1) -> bool:
        """Check if we can send to domain"""
        domain = domain.lower()
        bucket = self.domain_limits.get(domain, self.domain_limits['default'])
        return await bucket.consume(count)
    
    async def wait_for_domain_capacity(self, domain: str, count: int = 1, max_wait: float = 30.0) -> bool:
        """Wait for domain capacity"""
        domain = domain.lower()
        bucket = self.domain_limits.get(domain, self.domain_limits['default'])
        return await bucket.wait_for_tokens(count, max_wait)
    
    def get_domain_status(self, domain: str) -> Dict[str, Any]:
        """Get domain throttling status"""
        domain = domain.lower()
        bucket = self.domain_limits.get(domain, self.domain_limits['default'])
        return bucket.get_status()

class ESPRateLimiter:
    """
    ESP-specific rate limiting with multiple limit types
    """
    
    def __init__(self, esp_name: str, config: Dict[str, Any]):
        self.esp_name = esp_name
        self.config = config
        
        # Create token buckets for different limit types
        self.buckets = {}
        
        # Hourly limit
        if 'hourly_limit' in config:
            self.buckets[RateLimitType.HOURLY] = TokenBucket(
                rate=config['hourly_limit'] / 3600.0,  # Convert to per-second
                capacity=config['hourly_limit']
            )
        
        # Daily limit
        if 'daily_limit' in config:
            self.buckets[RateLimitType.DAILY] = TokenBucket(
                rate=config['daily_limit'] / 86400.0,  # Convert to per-second
                capacity=config['daily_limit']
            )
        
        # Burst limit (short-term high rate)
        if 'burst_limit' in config:
            self.buckets[RateLimitType.BURST] = TokenBucket(
                rate=config.get('burst_rate', 10.0),
                capacity=config['burst_limit']
            )
        
        # Domain throttling
        self.domain_throttler = DomainThrottler()
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'rate_limited_requests': 0,
            'last_reset': datetime.utcnow()
        }
    
    async def can_send(self, email_count: int = 1, recipient_domains: Optional[list] = None) -> Dict[str, Any]:
        """
        Check if ESP can send emails
        
        Args:
            email_count: Number of emails to send
            recipient_domains: List of recipient domains for domain throttling
            
        Returns:
            Dict with can_send status and details
        """
        self.stats['total_requests'] += 1
        
        result = {
            'can_send': True,
            'esp_name': self.esp_name,
            'email_count': email_count,
            'blocked_by': [],
            'wait_time': 0,
            'domain_status': {}
        }
        
        # Check ESP-level limits
        for limit_type, bucket in self.buckets.items():
            if not await bucket.consume(email_count):
                result['can_send'] = False
                result['blocked_by'].append(limit_type.value)
                
                # Calculate wait time
                bucket_status = bucket.get_status()
                wait_time = email_count / bucket.rate
                result['wait_time'] = max(result['wait_time'], wait_time)
        
        # Check domain throttling if domains provided
        if recipient_domains:
            domain_counts = {}
            for domain in recipient_domains:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
            
            for domain, count in domain_counts.items():
                can_send_domain = await self.domain_throttler.can_send_to_domain(domain, count)
                result['domain_status'][domain] = {
                    'can_send': can_send_domain,
                    'count': count,
                    'status': self.domain_throttler.get_domain_status(domain)
                }
                
                if not can_send_domain:
                    result['can_send'] = False
                    result['blocked_by'].append(f'domain_{domain}')
        
        # Update statistics
        if result['can_send']:
            self.stats['successful_requests'] += 1
        else:
            self.stats['rate_limited_requests'] += 1
        
        return result
    
    async def wait_for_capacity(self, email_count: int = 1, recipient_domains: Optional[list] = None, 
                               max_wait: float = 300.0) -> Dict[str, Any]:
        """
        Wait for capacity to become available
        
        Args:
            email_count: Number of emails to send
            recipient_domains: List of recipient domains
            max_wait: Maximum time to wait in seconds
            
        Returns:
            Dict with success status and details
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            result = await self.can_send(email_count, recipient_domains)
            
            if result['can_send']:
                return {
                    'success': True,
                    'waited_time': time.time() - start_time,
                    'result': result
                }
            
            # Wait based on the longest wait time needed
            wait_time = min(result['wait_time'], 10.0)  # Cap at 10 seconds
            await asyncio.sleep(wait_time)
        
        return {
            'success': False,
            'waited_time': time.time() - start_time,
            'timeout': True,
            'last_result': result
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive rate limiter status"""
        bucket_status = {}
        for limit_type, bucket in self.buckets.items():
            bucket_status[limit_type.value] = bucket.get_status()
        
        return {
            'esp_name': self.esp_name,
            'buckets': bucket_status,
            'statistics': self.stats,
            'config': self.config
        }
    
    def reset_statistics(self):
        """Reset statistics (useful for daily resets)"""
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'rate_limited_requests': 0,
            'last_reset': datetime.utcnow()
        }

class RateLimitManager:
    """
    Central rate limit manager for all ESPs
    """
    
    def __init__(self):
        self.esp_limiters = {}
        self.global_domain_throttler = DomainThrottler()
    
    def add_esp_limiter(self, esp_name: str, config: Dict[str, Any]):
        """Add ESP rate limiter"""
        self.esp_limiters[esp_name] = ESPRateLimiter(esp_name, config)
        logger.info(f"Added rate limiter for ESP: {esp_name}")
    
    async def can_esp_send(self, esp_name: str, email_count: int = 1, 
                          recipient_domains: Optional[list] = None) -> Dict[str, Any]:
        """Check if ESP can send emails"""
        if esp_name not in self.esp_limiters:
            return {
                'can_send': False,
                'error': f'No rate limiter configured for ESP: {esp_name}'
            }
        
        limiter = self.esp_limiters[esp_name]
        return await limiter.can_send(email_count, recipient_domains)
    
    async def wait_for_esp_capacity(self, esp_name: str, email_count: int = 1,
                                   recipient_domains: Optional[list] = None,
                                   max_wait: float = 300.0) -> Dict[str, Any]:
        """Wait for ESP capacity"""
        if esp_name not in self.esp_limiters:
            return {
                'success': False,
                'error': f'No rate limiter configured for ESP: {esp_name}'
            }
        
        limiter = self.esp_limiters[esp_name]
        return await limiter.wait_for_capacity(email_count, recipient_domains, max_wait)
    
    def get_all_status(self) -> Dict[str, Any]:
        """Get status for all ESP rate limiters"""
        status = {}
        for esp_name, limiter in self.esp_limiters.items():
            status[esp_name] = limiter.get_status()
        
        return {
            'esp_limiters': status,
            'global_domain_throttler': {
                domain: self.global_domain_throttler.get_domain_status(domain)
                for domain in ['gmail.com', 'outlook.com', 'yahoo.com', 'default']
            }
        }
    
    def reset_all_statistics(self):
        """Reset statistics for all limiters"""
        for limiter in self.esp_limiters.values():
            limiter.reset_statistics()
        logger.info("Reset statistics for all rate limiters")

# Global rate limit manager
rate_limit_manager = RateLimitManager()

# Initialize with default ESP configurations
default_esp_configs = {
    'sendgrid': {
        'hourly_limit': 100,
        'daily_limit': 1500,
        'burst_limit': 50,
        'burst_rate': 5.0
    },
    'amazon_ses': {
        'hourly_limit': 80,
        'daily_limit': 1000,
        'burst_limit': 40,
        'burst_rate': 4.0
    },
    'postmark': {
        'hourly_limit': 50,
        'daily_limit': 500,
        'burst_limit': 25,
        'burst_rate': 3.0
    }
}

for esp_name, config in default_esp_configs.items():
    rate_limit_manager.add_esp_limiter(esp_name, config)
