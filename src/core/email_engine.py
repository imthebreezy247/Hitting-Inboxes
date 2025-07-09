# src/core/email_engine.py
from typing import List, Dict, Optional, Tuple
import asyncio
from datetime import datetime, timedelta
import json
import time
from sqlalchemy.orm import Session
from .provider_manager import ProviderManager
from .warming_system import IPWarmingSchedule
from ..database.models import Subscriber, Campaign, Engagement
from ..utils.email_builder import OptimizedEmailBuilder

class EmailDeliveryEngine:
    def __init__(self, db_session: Session, config: Dict = None):
        self.db = db_session
        self.config = config or {}
        
        # Initialize components
        self.provider_manager = ProviderManager(db_session=db_session)
        self.warming_schedule = IPWarmingSchedule(target_volume=3000)
        self.email_builder = OptimizedEmailBuilder()
        
        # Rate limiting
        self.send_times = []
        self.hourly_sent = 0
        self.daily_sent = 0
        self.last_reset = datetime.now()
        
        # Performance tracking
        self.session_stats = {
            'sent': 0,
            'delivered': 0,
            'failed': 0,
            'start_time': datetime.now()
        }
    
    async def send_campaign(self, campaign_id: int, warming_mode: bool = False) -> Dict:
        """Send campaign with all optimizations"""
        
        campaign = self.db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        # Update campaign status
        campaign.status = 'sending'
        campaign.sent_time = datetime.now()
        self.db.commit()
        
        try:
            # Get sending limits
            if warming_mode:
                limits = self.warming_schedule.get_current_day_config()
                subscribers = self.warming_schedule.get_subscribers_for_warming(
                    self.db, self.warming_schedule.current_day
                )
            else:
                limits = {'daily_volume': 3000, 'hourly_limit': 600}
                subscribers = self._get_campaign_subscribers(campaign)
            
            # Limit subscribers based on daily volume
            subscribers = subscribers[:limits['daily_volume']]
            
            # Update campaign recipient count
            campaign.total_recipients = len(subscribers)
            self.db.commit()
            
            # Send emails in batches
            results = await self._send_email_batch(
                campaign, subscribers, limits, warming_mode
            )
            
            # Update campaign final status
            campaign.status = 'sent'
            campaign.sent_count = results['sent']
            campaign.delivered_count = results['delivered']
            campaign.bounce_count = results['bounced']
            campaign.complaint_count = results['complained']
            
            # Calculate rates
            if campaign.sent_count > 0:
                campaign.delivery_rate = campaign.delivered_count / campaign.sent_count
                campaign.bounce_rate = campaign.bounce_count / campaign.sent_count
            
            self.db.commit()
            
            return results
            
        except Exception as e:
            campaign.status = 'failed'
            self.db.commit()
            raise e
    
    def _get_campaign_subscribers(self, campaign: Campaign) -> List[Dict]:
        """Get subscribers for campaign based on segment rules"""
        query = self.db.query(Subscriber).filter(Subscriber.status == 'active')
        
        # Apply segment rules if specified
        if campaign.segment_rules:
            rules = campaign.segment_rules
            
            if 'min_engagement_score' in rules:
                query = query.filter(Subscriber.engagement_score >= rules['min_engagement_score'])
            
            if 'segments' in rules:
                query = query.filter(Subscriber.segment.in_(rules['segments']))
            
            if 'exclude_recent_campaigns' in rules:
                # Exclude subscribers who received emails recently
                days_ago = datetime.now() - timedelta(days=rules['exclude_recent_campaigns'])
                recent_sends = self.db.query(Engagement.subscriber_id).filter(
                    Engagement.sent_at >= days_ago
                ).subquery()
                query = query.filter(~Subscriber.id.in_(recent_sends))
        
        # Order by engagement score for better deliverability
        subscribers = query.order_by(Subscriber.engagement_score.desc()).all()
        
        return [
            {
                'id': sub.id,
                'email': sub.email,
                'name': sub.name,
                'company': sub.company,
                'engagement_score': sub.engagement_score,
                'time_zone': sub.time_zone or 'US/Eastern',
                'custom_fields': sub.custom_fields or {}
            }
            for sub in subscribers
        ]
    
    async def _send_email_batch(self, campaign: Campaign, subscribers: List[Dict], 
                               limits: Dict, warming_mode: bool) -> Dict:
        """Send emails in optimized batches"""
        results = {
            'sent': 0,
            'delivered': 0,
            'failed': 0,
            'bounced': 0,
            'complained': 0,
            'provider_stats': {},
            'errors': []
        }
        
        batch_size = min(50, limits.get('hourly_limit', 600) // 12)  # 12 batches per hour
        
        for i in range(0, len(subscribers), batch_size):
            batch = subscribers[i:i + batch_size]
            
            # Check rate limits
            if not self._check_rate_limits(len(batch), limits):
                await asyncio.sleep(300)  # Wait 5 minutes
                continue
            
            # Process batch
            batch_results = await self._process_batch(campaign, batch, warming_mode)
            
            # Update results
            for key in ['sent', 'delivered', 'failed', 'bounced', 'complained']:
                results[key] += batch_results.get(key, 0)
            
            # Update provider stats
            for provider, stats in batch_results.get('provider_stats', {}).items():
                if provider not in results['provider_stats']:
                    results['provider_stats'][provider] = {'sent': 0, 'failed': 0}
                results['provider_stats'][provider]['sent'] += stats.get('sent', 0)
                results['provider_stats'][provider]['failed'] += stats.get('failed', 0)
            
            # Add any errors
            results['errors'].extend(batch_results.get('errors', []))
            
            # Delay between batches
            if i + batch_size < len(subscribers):
                await asyncio.sleep(5)  # 5 second delay between batches
        
        return results
    
    async def _process_batch(self, campaign: Campaign, batch: List[Dict], 
                           warming_mode: bool) -> Dict:
        """Process a single batch of emails"""
        batch_results = {
            'sent': 0,
            'delivered': 0,
            'failed': 0,
            'bounced': 0,
            'complained': 0,
            'provider_stats': {},
            'errors': []
        }
        
        # Build email content once for the batch
        try:
            base_html, base_text = self.email_builder.build_email(
                campaign.html_content,
                {'subject': campaign.subject},
                {}
            )
        except Exception as e:
            batch_results['errors'].append(f"Email building failed: {str(e)}")
            batch_results['failed'] = len(batch)
            return batch_results

    async def _send_single_email(self, campaign: Campaign, subscriber: Dict,
                               base_html: str, base_text: str, warming_mode: bool) -> Dict:
        """Send a single email with provider selection and tracking"""

        # Personalize content for subscriber
        personalization_tokens = {
            'name': subscriber.get('name', 'Valued Customer'),
            'email': subscriber['email'],
            'company': subscriber.get('company', ''),
            'unsubscribe_link': f"https://cjsinsurancesolutions.com/unsubscribe?email={subscriber['email']}",
            'preferences_link': f"https://cjsinsurancesolutions.com/preferences?email={subscriber['email']}"
        }

        # Add custom fields
        personalization_tokens.update(subscriber.get('custom_fields', {}))

        try:
            # Personalize content
            html_content = self._personalize_content(base_html, personalization_tokens)
            text_content = self._personalize_content(base_text, personalization_tokens)

            # Select optimal provider
            provider = self.provider_manager.select_provider(
                subscriber['email'],
                subscriber.get('engagement_score', 0.5),
                {'campaign_id': campaign.id}
            )

            if not provider:
                return {
                    'success': False,
                    'error': 'No available email provider',
                    'provider': None
                }

            # Get optimal send time if enabled
            send_time = datetime.now()
            if campaign.send_time_optimization:
                optimal_time = self.provider_manager.get_best_send_time(
                    subscriber['email'],
                    subscriber.get('time_zone', 'US/Eastern')
                )
                if optimal_time > send_time:
                    # Schedule for later (in production, this would use a queue)
                    send_time = optimal_time

            # Create engagement record
            engagement = Engagement(
                subscriber_id=subscriber['id'],
                campaign_id=campaign.id,
                provider_used=provider.name,
                sent_at=send_time
            )
            self.db.add(engagement)
            self.db.commit()

            # Send email via provider
            success, message_id = await self._send_via_provider(
                provider,
                subscriber['email'],
                campaign.subject,
                html_content,
                text_content,
                campaign.from_name,
                campaign.from_email
            )

            # Update engagement record
            engagement.message_id = message_id
            if success:
                engagement.delivered_at = datetime.now()
                engagement.is_delivered = True

                # Update provider usage and reputation
                self.provider_manager.update_provider_usage(provider.name, 1)
                self.provider_manager.update_reputation(provider.name, 'delivered', campaign.id)
            else:
                engagement.bounced_at = datetime.now()
                engagement.is_bounced = True
                engagement.bounce_reason = message_id  # Error message

                # Update provider reputation
                self.provider_manager.update_reputation(provider.name, 'hard_bounce', campaign.id)

            self.db.commit()

            return {
                'success': success,
                'provider': provider.name,
                'message_id': message_id,
                'error': None if success else message_id
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'provider': provider.name if 'provider' in locals() else None
            }

    def _personalize_content(self, content: str, tokens: Dict) -> str:
        """Personalize content with subscriber data"""
        for token, value in tokens.items():
            placeholder = f"{{{{{token}}}}}"
            content = content.replace(placeholder, str(value or ''))
        return content

    async def _send_via_provider(self, provider, to_email: str, subject: str,
                               html_content: str, text_content: str,
                               from_name: str, from_email: str) -> Tuple[bool, str]:
        """Send email via specific provider"""

        try:
            if provider.name == 'sendgrid':
                return await self._send_via_sendgrid(
                    provider.client, to_email, subject, html_content,
                    text_content, from_name, from_email
                )
            elif provider.name == 'aws_ses':
                return await self._send_via_ses(
                    provider.client, to_email, subject, html_content,
                    text_content, from_name, from_email
                )
            elif provider.name == 'postmark':
                return await self._send_via_postmark(
                    provider.client, to_email, subject, html_content,
                    text_content, from_name, from_email
                )
            else:
                return False, f"Unknown provider: {provider.name}"

        except Exception as e:
            return False, str(e)

    async def _send_via_sendgrid(self, client, to_email: str, subject: str,
                               html_content: str, text_content: str,
                               from_name: str, from_email: str) -> Tuple[bool, str]:
        """Send via SendGrid"""
        try:
            from sendgrid.helpers.mail import Mail, Email, To, Content

            message = Mail(
                from_email=Email(from_email, from_name),
                to_emails=To(to_email),
                subject=subject,
                html_content=Content("text/html", html_content),
                plain_text_content=Content("text/plain", text_content)
            )

            # Add tracking and deliverability headers
            message.add_header('List-Unsubscribe', '<mailto:unsubscribe@cjsinsurancesolutions.com>')
            message.add_header('List-Unsubscribe-Post', 'List-Unsubscribe=One-Click')

            response = client.send(message)

            if response.status_code == 202:
                return True, "SendGrid: Email queued successfully"
            else:
                return False, f"SendGrid error: Status {response.status_code}"

        except Exception as e:
            return False, f"SendGrid error: {str(e)}"

    async def _send_via_ses(self, client, to_email: str, subject: str,
                          html_content: str, text_content: str,
                          from_name: str, from_email: str) -> Tuple[bool, str]:
        """Send via Amazon SES"""
        try:
            response = client.send_email(
                Source=f"{from_name} <{from_email}>",
                Destination={'ToAddresses': [to_email]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {
                        'Html': {'Data': html_content, 'Charset': 'UTF-8'},
                        'Text': {'Data': text_content, 'Charset': 'UTF-8'}
                    }
                }
            )

            message_id = response.get('MessageId')
            return True, message_id

        except Exception as e:
            return False, f"SES error: {str(e)}"

    async def _send_via_postmark(self, client, to_email: str, subject: str,
                               html_content: str, text_content: str,
                               from_name: str, from_email: str) -> Tuple[bool, str]:
        """Send via Postmark"""
        try:
            response = client.emails.send(
                From=f"{from_name} <{from_email}>",
                To=to_email,
                Subject=subject,
                HtmlBody=html_content,
                TextBody=text_content,
                MessageStream='broadcast'
            )

            return True, response.get('MessageID', 'Postmark: Sent')

        except Exception as e:
            return False, f"Postmark error: {str(e)}"

    def _check_rate_limits(self, batch_size: int, limits: Dict) -> bool:
        """Check if we can send batch without exceeding rate limits"""
        now = datetime.now()

        # Reset counters if needed
        if (now - self.last_reset).total_seconds() >= 3600:
            self.hourly_sent = 0
            self.last_reset = now

        if (now - self.last_reset).days >= 1:
            self.daily_sent = 0
            self.hourly_sent = 0
            self.last_reset = now

        # Check limits
        hourly_limit = limits.get('hourly_limit', 600)
        daily_limit = limits.get('daily_volume', 3000)

        if (self.hourly_sent + batch_size > hourly_limit or
            self.daily_sent + batch_size > daily_limit):
            return False

        return True

    def get_engine_stats(self) -> Dict:
        """Get current engine statistics"""
        runtime = (datetime.now() - self.session_stats['start_time']).total_seconds()

        return {
            'session_stats': self.session_stats,
            'runtime_seconds': runtime,
            'emails_per_minute': (self.session_stats['sent'] / (runtime / 60)) if runtime > 0 else 0,
            'success_rate': (self.session_stats['sent'] /
                           (self.session_stats['sent'] + self.session_stats['failed']))
                           if (self.session_stats['sent'] + self.session_stats['failed']) > 0 else 0,
            'provider_stats': self.provider_manager.get_provider_stats(),
            'warming_status': self.warming_schedule.get_warming_status(self.db, 'sendgrid')
        }
        
        # Send individual emails
        for subscriber in batch:
            try:
                result = await self._send_single_email(
                    campaign, subscriber, base_html, base_text, warming_mode
                )
                
                # Update batch results
                if result['success']:
                    batch_results['sent'] += 1
                    
                    # Update provider stats
                    provider = result['provider']
                    if provider not in batch_results['provider_stats']:
                        batch_results['provider_stats'][provider] = {'sent': 0, 'failed': 0}
                    batch_results['provider_stats'][provider]['sent'] += 1
                else:
                    batch_results['failed'] += 1
                    batch_results['errors'].append(f"{subscriber['email']}: {result['error']}")
                    
                    if result.get('provider'):
                        provider = result['provider']
                        if provider not in batch_results['provider_stats']:
                            batch_results['provider_stats'][provider] = {'sent': 0, 'failed': 0}
                        batch_results['provider_stats'][provider]['failed'] += 1
                
            except Exception as e:
                batch_results['failed'] += 1
                batch_results['errors'].append(f"{subscriber['email']}: {str(e)}")
        
        return batch_results
