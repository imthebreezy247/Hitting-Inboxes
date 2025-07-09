import aiohttp
import asyncio
import os
import json
import hmac
import hashlib
import base64
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests

class FeedbackLoopManager:
    def __init__(self, db_session):
        self.db = db_session
        self.domain = "cjsinsurancesolutions.com"
        self.mail_domain = f"mail.{self.domain}"
        
        # API credentials
        self.gmail_creds_file = 'config/gmail_postmaster_creds.json'
        self.outlook_api_key = os.environ.get('OUTLOOK_SNDS_API_KEY')
        self.yahoo_api_key = os.environ.get('YAHOO_FBL_API_KEY')
        
        self.feedback_endpoints = {
            'gmail': {
                'url': 'https://gmailpostmastertools.googleapis.com/v1beta1',
                'auth': 'oauth2',
                'metrics': ['reputation', 'spam_rate', 'auth_results', 'delivery_errors'],
                'setup_url': 'https://postmaster.google.com'
            },
            'outlook': {
                'url': 'https://sendersupport.olc.protection.outlook.com/snds/api',
                'auth': 'api_key',
                'metrics': ['reputation', 'complaint_rate', 'trap_hits', 'volume'],
                'setup_url': 'https://sendersupport.olc.protection.outlook.com/snds/'
            },
            'yahoo': {
                'url': 'https://senders.yahooinc.com/api/v1',
                'auth': 'api_key',
                'metrics': ['complaint_rate', 'delivery_rate', 'reputation'],
                'setup_url': 'https://senders.yahooinc.com/complaint-feedback-loop/'
            },
            'aol': {
                'url': 'https://postmaster.aol.com/api',
                'auth': 'basic',
                'metrics': ['fbl_reports', 'complaint_rate'],
                'setup_url': 'https://postmaster.aol.com/fbl-request'
            }
        }
        
    async def register_all_feedback_loops(self) -> Dict:
        """Register domain with all ISP feedback loops"""
        print("📡 Registering with ISP feedback loops...")
        
        registration_results = {}
        
        for isp, config in self.feedback_endpoints.items():
            try:
                print(f"📧 Registering with {isp.upper()}...")
                result = await self._register_feedback_loop(isp, config)
                registration_results[isp] = result
            except Exception as e:
                registration_results[isp] = {
                    'status': 'error',
                    'error': str(e),
                    'manual_setup_required': True
                }
        
        return {
            'registration_results': registration_results,
            'next_steps': self._get_registration_next_steps(registration_results),
            'estimated_setup_time': '2-5 business days for full activation'
        }
    
    async def _register_feedback_loop(self, isp: str, config: Dict) -> Dict:
        """Register with specific ISP feedback loop"""
        if isp == 'gmail':
            return await self._register_gmail_postmaster()
        elif isp == 'outlook':
            return await self._register_outlook_snds()
        elif isp == 'yahoo':
            return await self._register_yahoo_fbl()
        elif isp == 'aol':
            return await self._register_aol_fbl()
        else:
            return {'status': 'unknown_isp', 'error': f'Unknown ISP: {isp}'}
    
    async def _register_gmail_postmaster(self) -> Dict:
        """Register with Gmail Postmaster Tools"""
        verification_code = f"google-site-verification-{hashlib.md5(self.domain.encode()).hexdigest()[:16]}"
        
        return {
            'status': 'manual_verification_required',
            'isp': 'Gmail',
            'setup_steps': [
                '1. Go to https://postmaster.google.com',
                '2. Click "Add Domain" and enter: ' + self.mail_domain,
                '3. Add this DNS TXT record to verify ownership:',
                f'   Host: @ (root domain)',
                f'   Value: {verification_code}',
                '4. Click "Verify" in Google Postmaster Tools',
                '5. Create service account for API access',
                '6. Download credentials JSON file',
                '7. Save as config/gmail_postmaster_creds.json'
            ],
            'dns_record': {
                'type': 'TXT',
                'host': '@',
                'value': verification_code,
                'ttl': 300
            },
            'api_setup': {
                'service_account_required': True,
                'scopes': ['https://www.googleapis.com/auth/postmaster.readonly'],
                'credentials_file': self.gmail_creds_file
            },
            'benefits': [
                'Domain and IP reputation monitoring',
                'Spam rate tracking',
                'Authentication results',
                'Delivery error insights',
                'Feedback loop data'
            ]
        }
    
    async def _register_outlook_snds(self) -> Dict:
        """Register with Outlook SNDS (Smart Network Data Services)"""
        return {
            'status': 'manual_registration_required',
            'isp': 'Microsoft Outlook',
            'setup_steps': [
                '1. Go to https://sendersupport.olc.protection.outlook.com/snds/',
                '2. Click "Request Access"',
                '3. Provide your sending IP addresses',
                '4. Fill out the sender information form',
                '5. Wait for approval (1-3 business days)',
                '6. Once approved, get API key from dashboard',
                '7. Set OUTLOOK_SNDS_API_KEY environment variable'
            ],
            'required_information': [
                'Sending IP addresses',
                'Domain name',
                'Business information',
                'Email volume estimates',
                'Contact information'
            ],
            'api_access': {
                'endpoint': 'https://sendersupport.olc.protection.outlook.com/snds/api',
                'authentication': 'API key',
                'rate_limits': '1000 requests per day'
            },
            'benefits': [
                'IP reputation monitoring',
                'Complaint rate tracking',
                'Spam trap hit detection',
                'Volume and delivery data',
                'Junk mail reporting'
            ]
        }
    
    async def _register_yahoo_fbl(self) -> Dict:
        """Register with Yahoo Feedback Loop"""
        return {
            'status': 'manual_registration_required',
            'isp': 'Yahoo',
            'setup_steps': [
                '1. Go to https://senders.yahooinc.com/complaint-feedback-loop/',
                '2. Fill out the feedback loop request form',
                '3. Provide domain and IP information',
                '4. Submit business verification documents',
                '5. Wait for approval (3-5 business days)',
                '6. Configure webhook endpoint for FBL data',
                '7. Set YAHOO_FBL_API_KEY if API access granted'
            ],
            'webhook_setup': {
                'endpoint': f'https://{self.domain}/webhooks/yahoo-fbl',
                'method': 'POST',
                'content_type': 'application/json',
                'authentication': 'HMAC signature verification'
            },
            'required_documents': [
                'Business registration',
                'Domain ownership verification',
                'Email sending policy',
                'Privacy policy',
                'Unsubscribe process documentation'
            ],
            'benefits': [
                'Real-time complaint notifications',
                'Delivery rate insights',
                'Reputation monitoring',
                'Abuse report details'
            ]
        }
    
    async def _register_aol_fbl(self) -> Dict:
        """Register with AOL Feedback Loop"""
        return {
            'status': 'manual_registration_required',
            'isp': 'AOL',
            'setup_steps': [
                '1. Go to https://postmaster.aol.com/fbl-request',
                '2. Submit feedback loop request form',
                '3. Provide sender information and IPs',
                '4. Wait for approval (2-4 business days)',
                '5. Configure email endpoint for FBL reports',
                '6. Set up automated processing of FBL emails'
            ],
            'fbl_email_setup': {
                'endpoint': f'fbl-reports@{self.domain}',
                'format': 'ARF (Abuse Reporting Format)',
                'frequency': 'Real-time',
                'processing': 'Automated parsing required'
            },
            'benefits': [
                'Complaint notifications',
                'Abuse report details',
                'Sender reputation insights'
            ]
        }
    
    def _get_registration_next_steps(self, results: Dict) -> List[str]:
        """Get next steps for feedback loop registration"""
        next_steps = []
        
        for isp, result in results.items():
            if result.get('status') == 'manual_verification_required':
                next_steps.append(f"📧 Complete {isp.upper()} verification process")
            elif result.get('status') == 'manual_registration_required':
                next_steps.append(f"📝 Submit {isp.upper()} registration form")
            elif result.get('status') == 'error':
                next_steps.append(f"🔧 Fix {isp.upper()} configuration error")
        
        next_steps.extend([
            "⏰ Allow 2-5 business days for ISP approvals",
            "🔔 Set up webhook endpoints for real-time data",
            "📊 Configure automated FBL data processing",
            "🚨 Set up alerts for high complaint rates"
        ])
        
        return next_steps
    
    async def process_feedback_loop_data(self, isp: str, webhook_data: Dict):
        """Process incoming FBL data"""
        print(f"📨 Processing {isp.upper()} feedback loop data...")
        
        try:
            if isp == 'outlook':
                await self._process_outlook_fbl(webhook_data)
            elif isp == 'yahoo':
                await self._process_yahoo_fbl(webhook_data)
            elif isp == 'aol':
                await self._process_aol_fbl(webhook_data)
            elif isp == 'gmail':
                await self._process_gmail_fbl(webhook_data)
            
            # Store processed data
            await self._store_fbl_data(isp, webhook_data)
            
            # Check for alerts
            await self._check_fbl_alerts(isp, webhook_data)
            
        except Exception as e:
            print(f"❌ Error processing {isp} FBL data: {e}")
    
    async def _process_outlook_fbl(self, data: Dict):
        """Process Outlook/Hotmail FBL data"""
        # Process JMRP (Junk Mail Reporting Program) data
        if 'complaint' in data:
            complaint_data = data['complaint']
            
            # Extract relevant information
            message_id = complaint_data.get('message_id')
            recipient = complaint_data.get('recipient')
            complaint_type = complaint_data.get('type', 'spam')
            
            # Update subscriber status
            if recipient:
                await self._handle_complaint(recipient, complaint_type, 'outlook')
    
    async def _process_yahoo_fbl(self, data: Dict):
        """Process Yahoo FBL data"""
        if 'feedback_report' in data:
            report = data['feedback_report']
            
            # Extract complaint information
            message_id = report.get('original_mail_from')
            recipient = report.get('user_agent')
            feedback_type = report.get('feedback_type', 'abuse')
            
            if recipient:
                await self._handle_complaint(recipient, feedback_type, 'yahoo')
    
    async def _handle_complaint(self, email: str, complaint_type: str, isp: str):
        """Handle complaint by updating subscriber status"""
        try:
            from ..database.models import Subscriber
            
            # Find subscriber
            subscriber = self.db.query(Subscriber).filter_by(email=email).first()
            
            if subscriber:
                # Update subscriber status
                subscriber.status = 'complained'
                subscriber.complaint_date = datetime.now()
                subscriber.complaint_source = isp
                subscriber.complaint_type = complaint_type
                
                # Add to custom fields
                if not subscriber.custom_fields:
                    subscriber.custom_fields = {}
                
                subscriber.custom_fields['last_complaint'] = {
                    'date': datetime.now().isoformat(),
                    'type': complaint_type,
                    'source': isp
                }
                
                self.db.commit()
                print(f"🚨 Complaint processed: {email} ({complaint_type} from {isp})")
            
        except Exception as e:
            print(f"❌ Error handling complaint for {email}: {e}")
    
    async def get_isp_metrics(self) -> Dict:
        """Get current metrics from all ISPs"""
        print("📊 Fetching ISP metrics...")
        
        metrics = {
            'last_updated': datetime.now().isoformat(),
            'isps': {}
        }
        
        # Gmail Postmaster
        if os.path.exists(self.gmail_creds_file):
            try:
                metrics['isps']['gmail'] = await self._get_gmail_metrics()
            except Exception as e:
                metrics['isps']['gmail'] = {'error': str(e)}
        
        # Outlook SNDS
        if self.outlook_api_key:
            try:
                metrics['isps']['outlook'] = await self._get_outlook_metrics()
            except Exception as e:
                metrics['isps']['outlook'] = {'error': str(e)}
        
        # Yahoo
        if self.yahoo_api_key:
            try:
                metrics['isps']['yahoo'] = await self._get_yahoo_metrics()
            except Exception as e:
                metrics['isps']['yahoo'] = {'error': str(e)}
        
        return metrics
    
    async def _get_gmail_metrics(self) -> Dict:
        """Get Gmail Postmaster metrics"""
        try:
            # Load service account credentials
            credentials = service_account.Credentials.from_service_account_file(
                self.gmail_creds_file,
                scopes=['https://www.googleapis.com/auth/postmaster.readonly']
            )
            
            # Build service
            service = build('gmailpostmastertools', 'v1beta1', credentials=credentials)
            
            # Get domain reputation
            domain_name = f'domains/{self.mail_domain}'
            
            # Get reputation history (last 30 days)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            reputation_response = service.domains().trafficStats().list(
                parent=domain_name,
                startDate=start_date.strftime('%Y-%m-%d'),
                endDate=end_date.strftime('%Y-%m-%d')
            ).execute()
            
            return {
                'domain': self.mail_domain,
                'reputation_data': reputation_response.get('trafficStats', []),
                'status': 'active',
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'error': f'Gmail Postmaster API error: {str(e)}',
                'setup_required': True
            }
    
    async def _get_outlook_metrics(self) -> Dict:
        """Get Outlook SNDS metrics"""
        try:
            headers = {
                'Authorization': f'Bearer {self.outlook_api_key}',
                'Content-Type': 'application/json'
            }
            
            # Get IP reputation data
            response = requests.get(
                f'{self.feedback_endpoints["outlook"]["url"]}/reputation',
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'reputation_data': response.json(),
                    'status': 'active',
                    'last_updated': datetime.now().isoformat()
                }
            else:
                return {
                    'error': f'SNDS API error: {response.status_code}',
                    'response': response.text
                }
                
        except Exception as e:
            return {
                'error': f'Outlook SNDS error: {str(e)}',
                'setup_required': True
            }
    
    async def _get_yahoo_metrics(self) -> Dict:
        """Get Yahoo metrics"""
        try:
            headers = {
                'Authorization': f'Bearer {self.yahoo_api_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f'{self.feedback_endpoints["yahoo"]["url"]}/metrics',
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'metrics_data': response.json(),
                    'status': 'active',
                    'last_updated': datetime.now().isoformat()
                }
            else:
                return {
                    'error': f'Yahoo API error: {response.status_code}',
                    'response': response.text
                }
                
        except Exception as e:
            return {
                'error': f'Yahoo API error: {str(e)}',
                'setup_required': True
            }
    
    async def _store_fbl_data(self, isp: str, data: Dict):
        """Store FBL data in database"""
        try:
            # Store FBL data for analysis
            fbl_record = {
                'isp': isp,
                'received_at': datetime.now(),
                'data': json.dumps(data),
                'processed': True
            }
            
            # Add to database (implementation depends on your models)
            print(f"💾 Stored {isp} FBL data")
            
        except Exception as e:
            print(f"❌ Error storing FBL data: {e}")
    
    async def _check_fbl_alerts(self, isp: str, data: Dict):
        """Check for alert conditions in FBL data"""
        try:
            # Check complaint rate
            if 'complaint_rate' in data and data['complaint_rate'] > 0.1:
                await self._send_alert(
                    f"High complaint rate from {isp}: {data['complaint_rate']:.2%}",
                    'high'
                )
            
            # Check reputation drops
            if 'reputation' in data and data['reputation'] == 'poor':
                await self._send_alert(
                    f"Poor reputation reported by {isp}",
                    'critical'
                )
            
        except Exception as e:
            print(f"❌ Error checking FBL alerts: {e}")
    
    async def _send_alert(self, message: str, severity: str):
        """Send alert for FBL issues"""
        print(f"🚨 {severity.upper()} ALERT: {message}")
        
        # Here you would integrate with your alerting system
        # - Email notifications
        # - Slack/Discord webhooks
        # - SMS alerts
        # - Dashboard notifications
    
    def get_setup_status(self) -> Dict:
        """Get feedback loop setup status"""
        status = {
            'gmail': {
                'configured': os.path.exists(self.gmail_creds_file),
                'setup_url': self.feedback_endpoints['gmail']['setup_url'],
                'api_access': os.path.exists(self.gmail_creds_file)
            },
            'outlook': {
                'configured': bool(self.outlook_api_key),
                'setup_url': self.feedback_endpoints['outlook']['setup_url'],
                'api_access': bool(self.outlook_api_key)
            },
            'yahoo': {
                'configured': bool(self.yahoo_api_key),
                'setup_url': self.feedback_endpoints['yahoo']['setup_url'],
                'api_access': bool(self.yahoo_api_key)
            },
            'aol': {
                'configured': False,  # Manual setup only
                'setup_url': self.feedback_endpoints['aol']['setup_url'],
                'api_access': False
            }
        }
        
        configured_count = sum(1 for isp in status.values() if isp['configured'])
        
        return {
            'isps': status,
            'configured_count': configured_count,
            'total_isps': len(status),
            'completion_percentage': (configured_count / len(status)) * 100,
            'next_steps': [
                'Complete manual registrations for unconfigured ISPs',
                'Set up webhook endpoints for real-time data',
                'Configure automated alert thresholds',
                'Test FBL data processing'
            ]
        }
