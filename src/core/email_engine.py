# src/core/email_engine.py
import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

from ..database.models import get_db
from ..database.subscriber_manager import SubscriberManager
from ..database.engagement_tracker import EngagementTracker
from .provider_manager import ProviderManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class EmailDeliveryResult:
    """Result of email delivery operation"""
    success: bool
    sent_count: int
    failed_count: int
    failed_emails: List[str]
    esp_used: str
    message_ids: List[str]
    error_details: Optional[str] = None

@dataclass
class CampaignSendResult:
    """Result of campaign sending operation"""
    campaign_id: int
    total_recipients: int
    sent_count: int
    failed_count: int
    delivery_results: List[EmailDeliveryResult]
    start_time: datetime
    end_time: datetime
    esp_distribution: Dict[str, int]

class EmailDeliveryError(Exception):
    """Base exception for email delivery errors"""
    pass

class ESPConnectionError(EmailDeliveryError):
    """ESP connection specific errors"""
    pass

class RateLimitError(EmailDeliveryError):
    """Rate limiting errors"""
    pass

class EmailDeliveryEngine:
    """
    Advanced Email Delivery Engine with async support
    Handles campaign sending with multi-ESP support, rate limiting, and failover
    """
    
    def __init__(self, db_session):
        self.db = db_session
        self.provider_manager = ProviderManager(db_session=db_session)
        self.subscriber_manager = SubscriberManager(db_session)
        self.engagement_tracker = EngagementTracker(db_session)
        
        # Rate limiting configuration
        self.rate_limits = {
            'sendgrid': {'hourly': 100, 'daily': 1500, 'batch_size': 50},
            'amazon_ses': {'hourly': 80, 'daily': 1000, 'batch_size': 40},
            'postmark': {'hourly': 50, 'daily': 500, 'batch_size': 25}
        }
        
        # Circuit breaker state
        self.circuit_breakers = {}
        
    async def send_campaign(self, campaign_id: int, warming_mode: bool = False) -> CampaignSendResult:
        """
        Send email campaign with advanced features
        
        Args:
            campaign_id: ID of campaign to send
            warming_mode: Whether to use IP warming limits
            
        Returns:
            CampaignSendResult with detailed results
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting campaign {campaign_id} send (warming_mode={warming_mode})")
        
        try:
            # Get campaign details
            campaign = await self._get_campaign(campaign_id)
            if not campaign:
                raise EmailDeliveryError(f"Campaign {campaign_id} not found")
            
            # Get active subscribers for campaign
            subscribers = await self._get_campaign_subscribers(campaign_id, campaign.get('segment_rules'))
            if not subscribers:
                logger.warning(f"No subscribers found for campaign {campaign_id}")
                return self._create_empty_result(campaign_id, start_time)
            
            logger.info(f"Found {len(subscribers)} subscribers for campaign {campaign_id}")
            
            # Distribute subscribers across available ESPs
            esp_batches = await self._distribute_subscribers_across_esps(
                subscribers, warming_mode
            )
            
            # Send batches concurrently with rate limiting
            delivery_results = await self._send_batches_concurrently(
                campaign, esp_batches, warming_mode
            )
            
            # Calculate final results
            end_time = datetime.utcnow()
            result = self._calculate_campaign_results(
                campaign_id, subscribers, delivery_results, start_time, end_time
            )
            
            # Update campaign status
            await self._update_campaign_status(campaign_id, result)
            
            logger.info(f"Campaign {campaign_id} completed: {result.sent_count}/{result.total_recipients} sent")
            return result
            
        except Exception as e:
            logger.error(f"Campaign {campaign_id} failed: {str(e)}")
            end_time = datetime.utcnow()
            return CampaignSendResult(
                campaign_id=campaign_id,
                total_recipients=0,
                sent_count=0,
                failed_count=0,
                delivery_results=[],
                start_time=start_time,
                end_time=end_time,
                esp_distribution={},
            )
    
    async def _get_campaign(self, campaign_id: int) -> Optional[Dict]:
        """Get campaign details from database"""
        try:
            # This would be replaced with actual async database query
            query = """
                SELECT id, name, subject, html_content, text_content, 
                       from_name, from_email, segment_rules, status
                FROM campaigns 
                WHERE id = ? AND status IN ('draft', 'scheduled')
            """
            # Simulate async database call
            await asyncio.sleep(0.01)  # Remove in production
            
            # For now, return mock data - replace with actual DB query
            return {
                'id': campaign_id,
                'name': f'Campaign {campaign_id}',
                'subject': 'Test Subject',
                'html_content': '<html><body>Test Content</body></html>',
                'text_content': 'Test Content',
                'from_name': 'Chris - CJS Insurance Solutions',
                'from_email': 'chris@mail.cjsinsurancesolutions.com',
                'segment_rules': None,
                'status': 'draft'
            }
        except Exception as e:
            logger.error(f"Error getting campaign {campaign_id}: {str(e)}")
            return None
    
    async def _get_campaign_subscribers(self, campaign_id: int, segment_rules: Optional[Dict]) -> List[Dict]:
        """Get subscribers for campaign based on segment rules"""
        try:
            # This would be replaced with actual async database query
            await asyncio.sleep(0.01)  # Remove in production
            
            # Mock subscriber data - replace with actual DB query
            return [
                {
                    'id': 1,
                    'email': 'test1@example.com',
                    'name': 'Test User 1',
                    'engagement_score': 85.0,
                    'segment': 'general'
                },
                {
                    'id': 2,
                    'email': 'test2@example.com',
                    'name': 'Test User 2',
                    'engagement_score': 92.0,
                    'segment': 'vip'
                }
            ]
        except Exception as e:
            logger.error(f"Error getting subscribers for campaign {campaign_id}: {str(e)}")
            return []
    
    async def _distribute_subscribers_across_esps(self, subscribers: List[Dict], warming_mode: bool) -> Dict[str, List[Dict]]:
        """Distribute subscribers across available ESPs based on capacity and reputation"""
        esp_batches = {}
        
        # Get available ESPs
        available_esps = self.provider_manager.get_provider_stats()
        
        if not available_esps:
            logger.error("No ESPs available for sending")
            return esp_batches
        
        # Simple round-robin distribution for now
        # In production, this would consider ESP capacity, reputation, and warming limits
        esp_names = list(available_esps.keys())
        
        for i, subscriber in enumerate(subscribers):
            esp_name = esp_names[i % len(esp_names)]
            
            if esp_name not in esp_batches:
                esp_batches[esp_name] = []
            
            esp_batches[esp_name].append(subscriber)
        
        logger.info(f"Distributed {len(subscribers)} subscribers across {len(esp_batches)} ESPs")
        return esp_batches
    
    async def _send_batches_concurrently(self, campaign: Dict, esp_batches: Dict[str, List[Dict]], warming_mode: bool) -> List[EmailDeliveryResult]:
        """Send email batches concurrently with rate limiting"""
        tasks = []
        
        for esp_name, subscribers in esp_batches.items():
            if not subscribers:
                continue
                
            task = asyncio.create_task(
                self._send_esp_batch(campaign, esp_name, subscribers, warming_mode)
            )
            tasks.append(task)
        
        # Wait for all batches to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and return valid results
        delivery_results = []
        for result in results:
            if isinstance(result, EmailDeliveryResult):
                delivery_results.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Batch sending failed: {str(result)}")
        
        return delivery_results
    
    async def _send_esp_batch(self, campaign: Dict, esp_name: str, subscribers: List[Dict], warming_mode: bool) -> EmailDeliveryResult:
        """Send batch of emails via specific ESP with rate limiting"""
        logger.info(f"Sending batch of {len(subscribers)} emails via {esp_name}")
        
        # Check circuit breaker
        if self._is_circuit_breaker_open(esp_name):
            logger.warning(f"Circuit breaker open for {esp_name}, skipping batch")
            return EmailDeliveryResult(
                success=False,
                sent_count=0,
                failed_count=len(subscribers),
                failed_emails=[sub['email'] for sub in subscribers],
                esp_used=esp_name,
                message_ids=[],
                error_details="Circuit breaker open"
            )
        
        sent_count = 0
        failed_emails = []
        message_ids = []
        
        # Apply rate limiting
        batch_size = self.rate_limits.get(esp_name, {}).get('batch_size', 25)
        delay_between_batches = 2.0  # seconds
        
        for i in range(0, len(subscribers), batch_size):
            batch = subscribers[i:i + batch_size]
            
            try:
                # Send batch
                batch_result = await self._send_email_batch(campaign, esp_name, batch)
                
                sent_count += batch_result['sent_count']
                failed_emails.extend(batch_result['failed_emails'])
                message_ids.extend(batch_result['message_ids'])
                
                # Rate limiting delay
                if i + batch_size < len(subscribers):
                    await asyncio.sleep(delay_between_batches)
                    
            except Exception as e:
                logger.error(f"Batch send failed for {esp_name}: {str(e)}")
                failed_emails.extend([sub['email'] for sub in batch])
                self._record_circuit_breaker_failure(esp_name)
        
        return EmailDeliveryResult(
            success=sent_count > 0,
            sent_count=sent_count,
            failed_count=len(failed_emails),
            failed_emails=failed_emails,
            esp_used=esp_name,
            message_ids=message_ids
        )
    
    async def _send_email_batch(self, campaign: Dict, esp_name: str, subscribers: List[Dict]) -> Dict:
        """Send individual email batch via ESP"""
        # This is a mock implementation - replace with actual ESP integration
        await asyncio.sleep(0.1)  # Simulate network delay
        
        # Mock success rate of 95%
        import random
        sent_count = 0
        failed_emails = []
        message_ids = []
        
        for subscriber in subscribers:
            if random.random() < 0.95:  # 95% success rate
                sent_count += 1
                message_ids.append(f"msg_{esp_name}_{subscriber['id']}_{datetime.utcnow().timestamp()}")
            else:
                failed_emails.append(subscriber['email'])
        
        return {
            'sent_count': sent_count,
            'failed_emails': failed_emails,
            'message_ids': message_ids
        }
    
    def _is_circuit_breaker_open(self, esp_name: str) -> bool:
        """Check if circuit breaker is open for ESP"""
        breaker = self.circuit_breakers.get(esp_name)
        if not breaker:
            return False
        
        # Simple circuit breaker logic
        if breaker['failures'] >= 5 and breaker['last_failure'] > datetime.utcnow() - timedelta(minutes=5):
            return True
        
        return False
    
    def _record_circuit_breaker_failure(self, esp_name: str):
        """Record failure for circuit breaker"""
        if esp_name not in self.circuit_breakers:
            self.circuit_breakers[esp_name] = {'failures': 0, 'last_failure': None}
        
        self.circuit_breakers[esp_name]['failures'] += 1
        self.circuit_breakers[esp_name]['last_failure'] = datetime.utcnow()
    
    def _calculate_campaign_results(self, campaign_id: int, subscribers: List[Dict], 
                                  delivery_results: List[EmailDeliveryResult], 
                                  start_time: datetime, end_time: datetime) -> CampaignSendResult:
        """Calculate final campaign results"""
        total_sent = sum(result.sent_count for result in delivery_results)
        total_failed = sum(result.failed_count for result in delivery_results)
        
        esp_distribution = {}
        for result in delivery_results:
            esp_distribution[result.esp_used] = result.sent_count
        
        return CampaignSendResult(
            campaign_id=campaign_id,
            total_recipients=len(subscribers),
            sent_count=total_sent,
            failed_count=total_failed,
            delivery_results=delivery_results,
            start_time=start_time,
            end_time=end_time,
            esp_distribution=esp_distribution
        )
    
    async def _update_campaign_status(self, campaign_id: int, result: CampaignSendResult):
        """Update campaign status in database"""
        try:
            # Mock database update - replace with actual async DB operation
            await asyncio.sleep(0.01)
            logger.info(f"Updated campaign {campaign_id} status: {result.sent_count} sent")
        except Exception as e:
            logger.error(f"Error updating campaign {campaign_id} status: {str(e)}")
    
    def _create_empty_result(self, campaign_id: int, start_time: datetime) -> CampaignSendResult:
        """Create empty result for campaigns with no subscribers"""
        return CampaignSendResult(
            campaign_id=campaign_id,
            total_recipients=0,
            sent_count=0,
            failed_count=0,
            delivery_results=[],
            start_time=start_time,
            end_time=datetime.utcnow(),
            esp_distribution={}
        )
