# services/amazon_ses.py
import boto3
import os
from botocore.exceptions import ClientError, BotoCoreError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple
import json
from datetime import datetime

class AmazonSESService:
    def __init__(self):
        self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        
        if not self.aws_access_key or not self.aws_secret_key:
            raise ValueError("AWS credentials not found in environment variables")
        
        self.ses_client = boto3.client(
            'ses',
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            region_name=self.aws_region
        )
        
        self.from_email = os.getenv('SES_FROM_EMAIL', 'chris@mail.cjsinsurancesolutions.com')
        self.from_name = os.getenv('FROM_NAME', 'Chris - CJS Insurance Solutions')
    
    def verify_domain(self, domain: str) -> bool:
        """Verify domain with Amazon SES"""
        try:
            response = self.ses_client.verify_domain_identity(Domain=domain)
            print(f"Domain verification initiated for {domain}")
            print(f"Verification token: {response.get('VerificationToken')}")
            return True
        except ClientError as e:
            print(f"Error verifying domain: {e}")
            return False
    
    def get_domain_verification_status(self, domain: str) -> Dict:
        """Get domain verification status"""
        try:
            response = self.ses_client.get_identity_verification_attributes(
                Identities=[domain]
            )
            return response.get('VerificationAttributes', {}).get(domain, {})
        except ClientError as e:
            print(f"Error getting domain status: {e}")
            return {}
    
    def setup_dkim(self, domain: str) -> Dict:
        """Setup DKIM for domain"""
        try:
            response = self.ses_client.verify_domain_dkim(Domain=domain)
            return {
                'success': True,
                'dkim_tokens': response.get('DkimTokens', [])
            }
        except ClientError as e:
            print(f"Error setting up DKIM: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_sending_quota(self) -> Dict:
        """Get current sending quota and rate"""
        try:
            response = self.ses_client.get_send_quota()
            return {
                'max_24_hour': response.get('Max24HourSend', 0),
                'max_send_rate': response.get('MaxSendRate', 0),
                'sent_last_24_hours': response.get('SentLast24Hours', 0)
            }
        except ClientError as e:
            print(f"Error getting sending quota: {e}")
            return {}
    
    def send_email(self, to_email: str, subject: str, html_content: str, 
                   text_content: str, headers: Dict = None) -> Tuple[bool, str]:
        """Send individual email via Amazon SES"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            # Add custom headers
            if headers:
                for key, value in headers.items():
                    msg[key] = value
            
            # Add text and HTML parts
            text_part = MIMEText(text_content, 'plain', 'utf-8')
            html_part = MIMEText(html_content, 'html', 'utf-8')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Send email
            response = self.ses_client.send_raw_email(
                Source=self.from_email,
                Destinations=[to_email],
                RawMessage={'Data': msg.as_string()}
            )
            
            message_id = response.get('MessageId')
            return True, message_id
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"SES Error ({error_code}): {error_message}")
            return False, f"{error_code}: {error_message}"
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False, str(e)
    
    def send_bulk_email(self, recipients: List[Dict], subject: str, 
                       html_template: str, text_template: str) -> Tuple[int, List[str]]:
        """Send bulk emails with personalization"""
        sent_count = 0
        failed_emails = []
        
        for recipient in recipients:
            try:
                # Personalize content
                html_content = self._personalize_content(html_template, recipient)
                text_content = self._personalize_content(text_template, recipient)
                
                # Add tracking headers
                headers = {
                    'List-Unsubscribe': f'<mailto:unsubscribe@cjsinsurancesolutions.com?subject=Unsubscribe>',
                    'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
                    'X-Campaign-ID': recipient.get('campaign_id', 'unknown'),
                    'X-Subscriber-ID': recipient.get('subscriber_id', 'unknown')
                }
                
                success, message_id = self.send_email(
                    recipient['email'],
                    subject,
                    html_content,
                    text_content,
                    headers
                )
                
                if success:
                    sent_count += 1
                    print(f"SES: Sent to {recipient['email']} (ID: {message_id})")
                else:
                    failed_emails.append(recipient['email'])
                    print(f"SES: Failed to send to {recipient['email']}: {message_id}")
                    
            except Exception as e:
                failed_emails.append(recipient['email'])
                print(f"SES: Error sending to {recipient['email']}: {e}")
        
        return sent_count, failed_emails
    
    def _personalize_content(self, template: str, data: Dict) -> str:
        """Personalize email content with subscriber data"""
        content = template
        for key, value in data.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(value or ''))
        return content
    
    def get_bounce_and_complaint_notifications(self) -> Dict:
        """Get bounce and complaint notification settings"""
        try:
            response = self.ses_client.get_identity_notification_attributes(
                Identities=[self.from_email]
            )
            return response.get('NotificationAttributes', {})
        except ClientError as e:
            print(f"Error getting notification settings: {e}")
            return {}
    
    def setup_sns_notifications(self, topic_arn: str, notification_type: str) -> bool:
        """Setup SNS notifications for bounces and complaints"""
        try:
            self.ses_client.set_identity_notification_topic(
                Identity=self.from_email,
                NotificationType=notification_type,  # 'Bounce', 'Complaint', or 'Delivery'
                SnsTopic=topic_arn
            )
            return True
        except ClientError as e:
            print(f"Error setting up SNS notifications: {e}")
            return False
    
    def get_reputation_info(self) -> Dict:
        """Get reputation information"""
        try:
            response = self.ses_client.get_account_sending_enabled()
            quota = self.get_sending_quota()
            
            return {
                'sending_enabled': response.get('Enabled', False),
                'quota_info': quota,
                'reputation_status': 'healthy'  # SES doesn't provide direct reputation metrics
            }
        except ClientError as e:
            print(f"Error getting reputation info: {e}")
            return {'sending_enabled': False, 'error': str(e)}
