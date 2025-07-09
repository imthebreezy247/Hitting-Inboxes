# services/esp_manager.py
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from config.esp_config import ESPConfigManager, ESPProvider, ESPStatus
from services.amazon_ses import AmazonSESService
from services.postmark import PostmarkService
from database.models import db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ESPManager:
    def __init__(self):
        self.config_manager = ESPConfigManager()
        self.esp_services = {}
        self._initialize_services()
        
    def _initialize_services(self):
        """Initialize ESP service instances"""
        try:
            # Initialize SendGrid (already in email_sender.py)
            # We'll integrate it in the enhanced email_sender.py
            
            # Initialize Amazon SES
            if ESPProvider.AMAZON_SES in self.config_manager.configs:
                try:
                    self.esp_services[ESPProvider.AMAZON_SES] = AmazonSESService()
                    logger.info("Amazon SES service initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize Amazon SES: {e}")
            
            # Initialize Postmark
            if ESPProvider.POSTMARK in self.config_manager.configs:
                try:
                    self.esp_services[ESPProvider.POSTMARK] = PostmarkService()
                    logger.info("Postmark service initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize Postmark: {e}")
                    
        except Exception as e:
            logger.error(f"Error initializing ESP services: {e}")
    
    def get_optimal_esp(self, email_count: int = 1) -> Optional[ESPProvider]:
        """Get the optimal ESP for sending emails based on limits and reputation"""
        available_esps = self.config_manager.get_available_esps()
        
        for esp_config in available_esps:
            if esp_config.can_send(email_count):
                # Check if service is actually available
                if esp_config.provider in self.esp_services:
                    return esp_config.provider
        
        logger.warning("No available ESP found for sending")
        return None
    
    def send_email_with_failover(self, recipient_data: Dict, subject: str, 
                                html_content: str, text_content: str) -> Tuple[bool, str, ESPProvider]:
        """Send email with automatic failover to backup ESPs"""
        available_esps = self.config_manager.get_available_esps()
        
        for esp_config in available_esps:
            if not esp_config.can_send(1):
                continue
                
            provider = esp_config.provider
            
            if provider not in self.esp_services:
                continue
            
            try:
                success, message_id = self._send_via_esp(
                    provider,
                    recipient_data,
                    subject,
                    html_content,
                    text_content
                )
                
                if success:
                    # Update sent count
                    self.config_manager.update_sent_count(provider, 1)
                    
                    # Log successful send
                    self._log_send_attempt(provider, recipient_data['email'], True, message_id)
                    
                    return True, message_id, provider
                else:
                    # Log failed attempt
                    self._log_send_attempt(provider, recipient_data['email'], False, message_id)
                    
                    # If this ESP is having issues, reduce its reputation
                    current_score = esp_config.reputation_score
                    new_score = max(0, current_score - 5)
                    self.config_manager.update_reputation_score(provider, new_score)
                    
                    logger.warning(f"Failed to send via {provider.value}: {message_id}")
                    
            except Exception as e:
                logger.error(f"Error sending via {provider.value}: {e}")
                # Reduce reputation score for errors
                current_score = esp_config.reputation_score
                new_score = max(0, current_score - 10)
                self.config_manager.update_reputation_score(provider, new_score)
        
        return False, "All ESPs failed or unavailable", None
    
    def _send_via_esp(self, provider: ESPProvider, recipient_data: Dict, 
                     subject: str, html_content: str, text_content: str) -> Tuple[bool, str]:
        """Send email via specific ESP"""
        service = self.esp_services.get(provider)
        if not service:
            return False, "Service not available"
        
        # Add tracking headers
        headers = {
            'List-Unsubscribe': f'<mailto:unsubscribe@cjsinsurancesolutions.com?subject=Unsubscribe>',
            'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
            'X-Campaign-ID': recipient_data.get('campaign_id', 'unknown'),
            'X-Subscriber-ID': recipient_data.get('subscriber_id', 'unknown'),
            'X-ESP-Provider': provider.value
        }
        
        if provider == ESPProvider.AMAZON_SES:
            return service.send_email(
                recipient_data['email'],
                subject,
                html_content,
                text_content,
                headers
            )
        elif provider == ESPProvider.POSTMARK:
            return service.send_email(
                recipient_data['email'],
                subject,
                html_content,
                text_content,
                headers
            )
        # SendGrid will be handled in the enhanced email_sender.py
        
        return False, "Unknown provider"
    
    def send_bulk_with_distribution(self, recipients: List[Dict], subject: str, 
                                  html_template: str, text_template: str) -> Dict:
        """Send bulk emails distributed across available ESPs"""
        total_sent = 0
        total_failed = 0
        failed_emails = []
        esp_stats = {}
        
        # Get available ESPs and their capacities
        available_esps = self.config_manager.get_available_esps()
        
        if not available_esps:
            return {
                'total_sent': 0,
                'total_failed': len(recipients),
                'failed_emails': [r['email'] for r in recipients],
                'esp_stats': {}
            }
        
        # Distribute recipients across ESPs based on their capacity
        esp_batches = self._distribute_recipients(recipients, available_esps)
        
        for provider, batch_recipients in esp_batches.items():
            if not batch_recipients:
                continue
                
            try:
                service = self.esp_services.get(provider)
                if not service:
                    failed_emails.extend([r['email'] for r in batch_recipients])
                    total_failed += len(batch_recipients)
                    continue
                
                # Send batch via specific ESP
                if provider == ESPProvider.AMAZON_SES:
                    sent_count, batch_failed = service.send_bulk_email(
                        batch_recipients, subject, html_template, text_template
                    )
                elif provider == ESPProvider.POSTMARK:
                    sent_count, batch_failed = service.send_bulk_email(
                        batch_recipients, subject, html_template, text_template
                    )
                else:
                    # SendGrid will be handled separately
                    sent_count, batch_failed = 0, [r['email'] for r in batch_recipients]
                
                # Update statistics
                total_sent += sent_count
                total_failed += len(batch_failed)
                failed_emails.extend(batch_failed)
                
                esp_stats[provider.value] = {
                    'sent': sent_count,
                    'failed': len(batch_failed),
                    'total_attempted': len(batch_recipients)
                }
                
                # Update ESP sent counts
                self.config_manager.update_sent_count(provider, sent_count)
                
                # Add delay between ESP batches
                if sent_count > 0:
                    esp_config = self.config_manager.configs[provider]
                    time.sleep(esp_config.delay_between_batches)
                
            except Exception as e:
                logger.error(f"Error sending batch via {provider.value}: {e}")
                failed_emails.extend([r['email'] for r in batch_recipients])
                total_failed += len(batch_recipients)
        
        return {
            'total_sent': total_sent,
            'total_failed': total_failed,
            'failed_emails': failed_emails,
            'esp_stats': esp_stats
        }
    
    def _distribute_recipients(self, recipients: List[Dict], 
                             available_esps: List) -> Dict[ESPProvider, List[Dict]]:
        """Distribute recipients across ESPs based on capacity and priority"""
        distribution = {esp.provider: [] for esp in available_esps}
        
        # Calculate total available capacity
        total_capacity = sum(
            min(esp.daily_limit - esp.current_daily_sent, 
                esp.hourly_limit - esp.current_hourly_sent)
            for esp in available_esps
        )
        
        if total_capacity <= 0:
            return distribution
        
        recipient_index = 0
        
        for esp_config in available_esps:
            available_capacity = min(
                esp_config.daily_limit - esp_config.current_daily_sent,
                esp_config.hourly_limit - esp_config.current_hourly_sent
            )
            
            if available_capacity <= 0:
                continue
            
            # Calculate proportion based on capacity and reputation
            capacity_ratio = available_capacity / total_capacity
            reputation_factor = esp_config.reputation_score / 100.0
            adjusted_ratio = capacity_ratio * reputation_factor
            
            # Assign recipients
            batch_size = min(
                int(len(recipients) * adjusted_ratio),
                available_capacity,
                len(recipients) - recipient_index
            )
            
            if batch_size > 0:
                distribution[esp_config.provider] = recipients[recipient_index:recipient_index + batch_size]
                recipient_index += batch_size
        
        # Assign remaining recipients to the highest priority ESP with capacity
        if recipient_index < len(recipients):
            for esp_config in available_esps:
                remaining_capacity = min(
                    esp_config.daily_limit - esp_config.current_daily_sent,
                    esp_config.hourly_limit - esp_config.current_hourly_sent
                ) - len(distribution[esp_config.provider])
                
                if remaining_capacity > 0:
                    remaining_recipients = recipients[recipient_index:]
                    additional_batch = remaining_recipients[:remaining_capacity]
                    distribution[esp_config.provider].extend(additional_batch)
                    recipient_index += len(additional_batch)
                    
                    if recipient_index >= len(recipients):
                        break
        
        return distribution
    
    def _log_send_attempt(self, provider: ESPProvider, email: str, 
                         success: bool, message_id: str):
        """Log send attempt to database"""
        try:
            db.execute_update('''
                INSERT INTO email_sends (email, esp_provider, status, message_id, sent_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                email,
                provider.value,
                'sent' if success else 'failed',
                message_id,
                datetime.now().isoformat()
            ))
        except Exception as e:
            logger.error(f"Error logging send attempt: {e}")
    
    def get_esp_performance_stats(self) -> Dict:
        """Get performance statistics for all ESPs"""
        stats = {}
        
        for provider in ESPProvider:
            if provider in self.config_manager.configs:
                config = self.config_manager.configs[provider]
                
                # Get recent performance from database
                recent_sends = db.execute_query('''
                    SELECT status, COUNT(*) as count
                    FROM email_sends 
                    WHERE esp_provider = ? AND sent_time > datetime('now', '-24 hours')
                    GROUP BY status
                ''', (provider.value,))
                
                sent_count = sum(row['count'] for row in recent_sends if row['status'] == 'sent')
                failed_count = sum(row['count'] for row in recent_sends if row['status'] == 'failed')
                
                stats[provider.value] = {
                    'status': config.status.value,
                    'reputation_score': config.reputation_score,
                    'daily_limit': config.daily_limit,
                    'current_daily_sent': config.current_daily_sent,
                    'recent_sent': sent_count,
                    'recent_failed': failed_count,
                    'success_rate': (sent_count / (sent_count + failed_count) * 100) if (sent_count + failed_count) > 0 else 0
                }
        
        return stats
