# services/postmark.py
import requests
import os
from typing import Dict, List, Optional, Tuple
import json
from datetime import datetime

class PostmarkService:
    def __init__(self):
        self.api_key = os.getenv('POSTMARK_API_KEY')
        self.server_token = os.getenv('POSTMARK_SERVER_TOKEN', self.api_key)
        
        if not self.api_key:
            raise ValueError("Postmark API key not found in environment variables")
        
        self.base_url = "https://api.postmarkapp.com"
        self.from_email = os.getenv('POSTMARK_FROM_EMAIL', 'chris@mail.cjsinsurancesolutions.com')
        self.from_name = os.getenv('FROM_NAME', 'Chris - CJS Insurance Solutions')
        
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Postmark-Server-Token': self.server_token
        }
    
    def verify_domain(self, domain: str) -> Dict:
        """Add and verify domain with Postmark"""
        try:
            data = {
                'Name': domain,
                'ReturnPathDomain': domain
            }
            
            response = requests.post(
                f"{self.base_url}/domains",
                headers=self.headers,
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'domain_id': result.get('ID'),
                    'dkim_tokens': result.get('DKIMTokens', []),
                    'verification_token': result.get('VerificationToken')
                }
            else:
                return {
                    'success': False,
                    'error': response.text
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_domain_status(self, domain_id: int) -> Dict:
        """Get domain verification status"""
        try:
            response = requests.get(
                f"{self.base_url}/domains/{domain_id}",
                headers=self.headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}
                
        except Exception as e:
            return {'error': str(e)}
    
    def send_email(self, to_email: str, subject: str, html_content: str, 
                   text_content: str, headers: Dict = None) -> Tuple[bool, str]:
        """Send individual email via Postmark"""
        try:
            data = {
                'From': f"{self.from_name} <{self.from_email}>",
                'To': to_email,
                'Subject': subject,
                'HtmlBody': html_content,
                'TextBody': text_content,
                'MessageStream': 'broadcast'  # Use broadcast stream for marketing emails
            }
            
            # Add custom headers
            if headers:
                data['Headers'] = [
                    {'Name': key, 'Value': value} 
                    for key, value in headers.items()
                ]
            
            response = requests.post(
                f"{self.base_url}/email",
                headers=self.headers,
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                message_id = result.get('MessageID')
                return True, message_id
            else:
                error_info = response.json() if response.headers.get('content-type') == 'application/json' else response.text
                return False, str(error_info)
                
        except Exception as e:
            return False, str(e)
    
    def send_bulk_email(self, recipients: List[Dict], subject: str, 
                       html_template: str, text_template: str) -> Tuple[int, List[str]]:
        """Send bulk emails with personalization"""
        sent_count = 0
        failed_emails = []
        
        # Postmark supports batch sending up to 500 emails
        batch_size = 500
        
        for i in range(0, len(recipients), batch_size):
            batch = recipients[i:i + batch_size]
            batch_emails = []
            
            for recipient in batch:
                try:
                    # Personalize content
                    html_content = self._personalize_content(html_template, recipient)
                    text_content = self._personalize_content(text_template, recipient)
                    
                    email_data = {
                        'From': f"{self.from_name} <{self.from_email}>",
                        'To': recipient['email'],
                        'Subject': subject,
                        'HtmlBody': html_content,
                        'TextBody': text_content,
                        'MessageStream': 'broadcast',
                        'Headers': [
                            {'Name': 'List-Unsubscribe', 'Value': f'<mailto:unsubscribe@cjsinsurancesolutions.com?subject=Unsubscribe>'},
                            {'Name': 'X-Campaign-ID', 'Value': recipient.get('campaign_id', 'unknown')},
                            {'Name': 'X-Subscriber-ID', 'Value': recipient.get('subscriber_id', 'unknown')}
                        ]
                    }
                    
                    batch_emails.append(email_data)
                    
                except Exception as e:
                    failed_emails.append(recipient['email'])
                    print(f"Postmark: Error preparing email for {recipient['email']}: {e}")
            
            # Send batch
            if batch_emails:
                try:
                    response = requests.post(
                        f"{self.base_url}/email/batch",
                        headers=self.headers,
                        json=batch_emails
                    )
                    
                    if response.status_code == 200:
                        results = response.json()
                        for i, result in enumerate(results):
                            if result.get('ErrorCode') == 0:
                                sent_count += 1
                                print(f"Postmark: Sent to {batch[i]['email']} (ID: {result.get('MessageID')})")
                            else:
                                failed_emails.append(batch[i]['email'])
                                print(f"Postmark: Failed to send to {batch[i]['email']}: {result.get('Message')}")
                    else:
                        # If batch fails, mark all as failed
                        for recipient in batch:
                            failed_emails.append(recipient['email'])
                        print(f"Postmark: Batch send failed: {response.text}")
                        
                except Exception as e:
                    # If batch fails, mark all as failed
                    for recipient in batch:
                        failed_emails.append(recipient['email'])
                    print(f"Postmark: Batch send error: {e}")
        
        return sent_count, failed_emails
    
    def _personalize_content(self, template: str, data: Dict) -> str:
        """Personalize email content with subscriber data"""
        content = template
        for key, value in data.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(value or ''))
        return content
    
    def get_server_info(self) -> Dict:
        """Get server information and limits"""
        try:
            response = requests.get(
                f"{self.base_url}/server",
                headers=self.headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}
                
        except Exception as e:
            return {'error': str(e)}
    
    def get_delivery_stats(self, tag: str = None) -> Dict:
        """Get delivery statistics"""
        try:
            url = f"{self.base_url}/deliverystats"
            if tag:
                url += f"?tag={tag}"
            
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}
                
        except Exception as e:
            return {'error': str(e)}
    
    def get_bounces(self, count: int = 100, offset: int = 0) -> Dict:
        """Get bounce information"""
        try:
            response = requests.get(
                f"{self.base_url}/bounces?count={count}&offset={offset}",
                headers=self.headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.text}
                
        except Exception as e:
            return {'error': str(e)}
    
    def activate_bounce(self, bounce_id: int) -> bool:
        """Activate a bounced email address"""
        try:
            response = requests.put(
                f"{self.base_url}/bounces/{bounce_id}/activate",
                headers=self.headers
            )
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"Error activating bounce: {e}")
            return False
