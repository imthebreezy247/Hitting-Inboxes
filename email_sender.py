# email_sender.py
import os
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from email_validator import validate_email, EmailNotValidError
import pandas as pd
from datetime import datetime
import time
from dotenv import load_dotenv
from typing import Dict, List, Tuple, Optional

# Import new services
from services.esp_manager import ESPManager
from config.esp_config import ESPProvider, ESPConfigManager
from database.models import db

load_dotenv()

class EmailDeliverySystem:
    def __init__(self):
        # Initialize SendGrid (legacy support)
        self.sg = sendgrid.SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))
        self.from_email = os.environ.get('FROM_EMAIL', 'chris@mail.cjsinsurancesolutions.com')
        self.from_name = os.environ.get('FROM_NAME', 'Chris - CJS Insurance Solutions')

        # Initialize multi-ESP manager
        self.esp_manager = ESPManager()
        self.config_manager = ESPConfigManager()

        # Default settings (can be overridden by ESP configs)
        self.daily_limit = 3000
        self.batch_size = 100
        self.delay_between_batches = 5  # seconds
        
    def validate_email_list(self, email_list):
        """Validate and clean email list"""
        valid_emails = []
        invalid_emails = []
        
        for email in email_list:
            try:
                validated = validate_email(email)
                valid_emails.append(validated.email)
            except EmailNotValidError:
                invalid_emails.append(email)
                
        return valid_emails, invalid_emails
    
    def create_personalized_content(self, template, subscriber_data):
        """Personalize email content for each subscriber"""
        content = template
        for key, value in subscriber_data.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(value))
        return content
    
    def send_batch_emails(self, subscribers, subject, html_template, text_template,
                         campaign_id: Optional[int] = None):
        """Send emails using multi-ESP system with failover"""
        # Use new multi-ESP system
        results = self.esp_manager.send_bulk_with_distribution(
            subscribers, subject, html_template, text_template
        )

        # Log campaign results if campaign_id provided
        if campaign_id:
            self._log_campaign_results(campaign_id, results)

        return results['total_sent'], results['failed_emails']

    def send_single_email_with_failover(self, subscriber: Dict, subject: str,
                                      html_content: str, text_content: str) -> Tuple[bool, str]:
        """Send single email with ESP failover"""
        success, message_id, provider = self.esp_manager.send_email_with_failover(
            subscriber, subject, html_content, text_content
        )

        if success:
            print(f"Sent to {subscriber['email']} via {provider.value if provider else 'unknown'} (ID: {message_id})")
        else:
            print(f"Failed to send to {subscriber['email']}: {message_id}")

        return success, message_id

    def send_via_sendgrid(self, subscriber: Dict, subject: str,
                         html_content: str, text_content: str) -> Tuple[bool, str]:
        """Send email specifically via SendGrid (legacy method)"""
        try:
            # Create message
            message = Mail(
                from_email=Email(self.from_email, self.from_name),
                to_emails=To(subscriber['email']),
                subject=subject,
                html_content=Content("text/html", html_content),
                plain_text_content=Content("text/plain", text_content)
            )

            # Add headers for better deliverability
            message.reply_to = Email(self.from_email)
            message.add_header('List-Unsubscribe', f'<mailto:unsubscribe@cjsinsurancesolutions.com?subject=Unsubscribe>')
            message.add_header('List-Unsubscribe-Post', 'List-Unsubscribe=One-Click')
            message.add_header('X-ESP-Provider', 'sendgrid')

            # Add campaign tracking headers if available
            if 'campaign_id' in subscriber:
                message.add_header('X-Campaign-ID', str(subscriber['campaign_id']))
            if 'subscriber_id' in subscriber:
                message.add_header('X-Subscriber-ID', str(subscriber['subscriber_id']))

            # Send email
            response = self.sg.send(message)

            if response.status_code == 202:
                return True, "SendGrid: Email sent successfully"
            else:
                return False, f"SendGrid error: Status {response.status_code}"

        except Exception as e:
            return False, f"SendGrid error: {str(e)}"

    def _log_campaign_results(self, campaign_id: int, results: Dict):
        """Log campaign results to database"""
        try:
            db.execute_update('''
                UPDATE campaigns
                SET sent_count = ?,
                    total_recipients = ?,
                    sent_time = ?,
                    status = 'sent'
                WHERE id = ?
            ''', (
                results['total_sent'],
                results['total_sent'] + results['total_failed'],
                datetime.now().isoformat(),
                campaign_id
            ))
        except Exception as e:
            print(f"Error logging campaign results: {e}")

    def get_esp_status(self) -> Dict:
        """Get status of all configured ESPs"""
        return self.esp_manager.get_esp_performance_stats()

    def get_optimal_esp(self, email_count: int = 1) -> Optional[str]:
        """Get the optimal ESP for sending emails"""
        esp = self.esp_manager.get_optimal_esp(email_count)
        return esp.value if esp else None

    def reset_daily_limits(self):
        """Reset daily limits for all ESPs"""
        self.config_manager.reset_daily_limits()

    def reset_hourly_limits(self):
        """Reset hourly limits for all ESPs"""
        self.config_manager.reset_hourly_limits()