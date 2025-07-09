import requests
import re
import os
import asyncio
import hashlib
import base64
from typing import Dict, Tuple, List
from datetime import datetime
import json

class SpamTestingServices:
    def __init__(self):
        self.glockapps_api_key = os.environ.get('GLOCKAPPS_API_KEY')
        self.litmus_api_key = os.environ.get('LITMUS_API_KEY')
        self.mail_tester_base_url = "https://www.mail-tester.com"
        
    async def test_with_mail_tester(self, html_content: str, from_email: str, subject: str) -> Dict:
        """Test email with mail-tester.com"""
        try:
            # Generate unique test address
            test_id = hashlib.md5(f"{datetime.now().isoformat()}".encode()).hexdigest()[:10]
            test_email = f"test-{test_id}@mail-tester.com"
            
            print(f"📧 Testing with Mail-Tester: {test_email}")
            
            # Send test email (would use actual email engine)
            # For now, simulate the process
            await self._simulate_mail_tester_send(test_email, html_content, subject)
            
            # Wait for processing
            await asyncio.sleep(30)
            
            # Get results
            try:
                response = requests.get(f"{self.mail_tester_base_url}/test-{test_id}", timeout=30)
                
                # Parse score
                score_match = re.search(r'Your score:\s*(\d+\.?\d*)/10', response.text)
                score = float(score_match.group(1)) if score_match else 0
                
                # Parse issues
                issues = self._parse_mail_tester_issues(response.text)
                
                return {
                    'service': 'mail-tester',
                    'score': score,
                    'max_score': 10,
                    'percentage': (score / 10) * 100,
                    'issues': issues,
                    'test_url': f"{self.mail_tester_base_url}/test-{test_id}",
                    'recommendations': self._get_spam_recommendations(score, issues),
                    'status': 'pass' if score >= 8 else 'warning' if score >= 6 else 'fail'
                }
                
            except requests.RequestException as e:
                return {
                    'service': 'mail-tester',
                    'error': f"Failed to get results: {str(e)}",
                    'score': 0
                }
                
        except Exception as e:
            return {
                'service': 'mail-tester',
                'error': str(e),
                'score': 0
            }
    
    async def _simulate_mail_tester_send(self, test_email: str, html_content: str, subject: str):
        """Simulate sending email to Mail-Tester"""
        # In production, this would use your actual email engine
        print(f"📤 Simulating send to {test_email}")
        
        # Simulate realistic score based on content analysis
        spam_indicators = self._analyze_content_for_spam(html_content + subject)
        return len(spam_indicators)
    
    def _analyze_content_for_spam(self, content: str) -> List[str]:
        """Analyze content for spam indicators"""
        spam_words = [
            'free', 'guarantee', 'urgent', 'act now', 'limited time',
            'click here', 'buy now', 'special offer', 'congratulations',
            'winner', 'cash', 'money', 'income', 'earn', 'profit'
        ]
        
        found_indicators = []
        content_lower = content.lower()
        
        for word in spam_words:
            if word in content_lower:
                found_indicators.append(word)
        
        # Check for excessive punctuation
        if content.count('!') > 3:
            found_indicators.append('excessive_exclamation')
        
        # Check for all caps
        if len([c for c in content if c.isupper()]) / len(content) > 0.3:
            found_indicators.append('excessive_caps')
        
        return found_indicators
    
    def _parse_mail_tester_issues(self, html_content: str) -> List[Dict]:
        """Parse issues from Mail-Tester response"""
        issues = []
        
        # Look for common issue patterns
        issue_patterns = {
            'spf_fail': r'SPF.*fail',
            'dkim_fail': r'DKIM.*fail',
            'dmarc_fail': r'DMARC.*fail',
            'blacklist': r'blacklist',
            'spam_words': r'spam.*word',
            'missing_unsubscribe': r'unsubscribe.*link'
        }
        
        for issue_type, pattern in issue_patterns.items():
            if re.search(pattern, html_content, re.IGNORECASE):
                issues.append({
                    'type': issue_type,
                    'severity': 'high' if issue_type in ['blacklist', 'spf_fail'] else 'medium',
                    'description': f"Issue detected: {issue_type.replace('_', ' ').title()}"
                })
        
        return issues
    
    def _get_spam_recommendations(self, score: float, issues: List[Dict]) -> List[str]:
        """Get recommendations based on spam test results"""
        recommendations = []
        
        if score < 6:
            recommendations.append("🚨 Critical: Score too low for reliable delivery")
            recommendations.append("🔧 Fix authentication issues (SPF/DKIM/DMARC)")
            recommendations.append("📝 Remove spam trigger words from content")
        elif score < 8:
            recommendations.append("⚠️ Warning: Score could be improved")
            recommendations.append("🎯 Optimize content to reduce spam indicators")
        else:
            recommendations.append("✅ Excellent spam score - good for delivery")
        
        # Specific recommendations based on issues
        for issue in issues:
            if issue['type'] == 'spf_fail':
                recommendations.append("🔐 Fix SPF record configuration")
            elif issue['type'] == 'dkim_fail':
                recommendations.append("🔑 Configure DKIM signing properly")
            elif issue['type'] == 'missing_unsubscribe':
                recommendations.append("📧 Add clear unsubscribe link")
        
        return recommendations
    
    async def test_with_glockapps(self, campaign_data: Dict) -> Dict:
        """Run comprehensive inbox placement test with GlockApps"""
        if not self.glockapps_api_key:
            return {
                'service': 'glockapps',
                'error': 'API key not configured',
                'setup_instructions': [
                    '1. Sign up at https://glockapps.com',
                    '2. Get API key from dashboard',
                    '3. Set GLOCKAPPS_API_KEY environment variable'
                ]
            }
        
        try:
            # Create test
            response = requests.post(
                'https://api.glockapps.com/v1/tests',
                headers={'Authorization': f'Bearer {self.glockapps_api_key}'},
                json={
                    'name': f'Campaign {campaign_data.get("id", "test")} Test',
                    'from': campaign_data.get('from_email'),
                    'subject': campaign_data.get('subject'),
                    'html': campaign_data.get('html_content'),
                    'text': campaign_data.get('text_content')
                },
                timeout=30
            )
            
            if response.status_code != 201:
                return {
                    'service': 'glockapps',
                    'error': f'Failed to create test: {response.status_code}',
                    'response': response.text
                }
            
            test_id = response.json()['id']
            print(f"📊 GlockApps test created: {test_id}")
            
            # Wait for results
            print("⏳ Waiting for GlockApps results (5 minutes)...")
            await asyncio.sleep(300)  # 5 minutes
            
            # Get results
            results_response = requests.get(
                f'https://api.glockapps.com/v1/tests/{test_id}/results',
                headers={'Authorization': f'Bearer {self.glockapps_api_key}'},
                timeout=30
            )
            
            if results_response.status_code == 200:
                return self._parse_glockapps_results(results_response.json())
            else:
                return {
                    'service': 'glockapps',
                    'error': f'Failed to get results: {results_response.status_code}',
                    'test_id': test_id
                }
                
        except requests.RequestException as e:
            return {
                'service': 'glockapps',
                'error': f'Request failed: {str(e)}'
            }
        except Exception as e:
            return {
                'service': 'glockapps',
                'error': str(e)
            }
    
    def _parse_glockapps_results(self, data: Dict) -> Dict:
        """Parse GlockApps results into actionable insights"""
        try:
            return {
                'service': 'glockapps',
                'inbox_rate': data.get('inboxRate', 0),
                'spam_rate': data.get('spamRate', 0),
                'missing_rate': data.get('missingRate', 0),
                'promotions_rate': data.get('promotionsRate', 0),
                'providers': {
                    'gmail': data.get('providers', {}).get('gmail', {}),
                    'outlook': data.get('providers', {}).get('outlook', {}),
                    'yahoo': data.get('providers', {}).get('yahoo', {}),
                    'apple': data.get('providers', {}).get('apple', {})
                },
                'authentication': {
                    'spf': data.get('authentication', {}).get('spf', 'unknown'),
                    'dkim': data.get('authentication', {}).get('dkim', 'unknown'),
                    'dmarc': data.get('authentication', {}).get('dmarc', 'unknown')
                },
                'content_analysis': data.get('contentAnalysis', {}),
                'recommendations': data.get('recommendations', []),
                'test_url': data.get('testUrl', ''),
                'status': 'pass' if data.get('inboxRate', 0) >= 80 else 'warning' if data.get('inboxRate', 0) >= 60 else 'fail'
            }
        except Exception as e:
            return {
                'service': 'glockapps',
                'error': f'Failed to parse results: {str(e)}',
                'raw_data': data
            }
    
    async def test_with_litmus(self, campaign_data: Dict) -> Dict:
        """Test email rendering and spam with Litmus"""
        if not self.litmus_api_key:
            return {
                'service': 'litmus',
                'error': 'API key not configured',
                'setup_instructions': [
                    '1. Sign up at https://litmus.com',
                    '2. Get API key from account settings',
                    '3. Set LITMUS_API_KEY environment variable'
                ]
            }
        
        try:
            # Create email test
            response = requests.post(
                'https://api.litmus.com/v1/emails',
                headers={
                    'Authorization': f'Basic {base64.b64encode(f"{self.litmus_api_key}:".encode()).decode()}',
                    'Content-Type': 'application/json'
                },
                json={
                    'subject': campaign_data.get('subject'),
                    'html_body': campaign_data.get('html_content'),
                    'text_body': campaign_data.get('text_content'),
                    'from_name': campaign_data.get('from_name'),
                    'from_email': campaign_data.get('from_email')
                },
                timeout=30
            )
            
            if response.status_code == 201:
                test_data = response.json()
                return {
                    'service': 'litmus',
                    'test_id': test_data.get('id'),
                    'test_url': test_data.get('url'),
                    'status': 'created',
                    'message': 'Test created successfully. Check Litmus dashboard for results.'
                }
            else:
                return {
                    'service': 'litmus',
                    'error': f'Failed to create test: {response.status_code}',
                    'response': response.text
                }
                
        except Exception as e:
            return {
                'service': 'litmus',
                'error': str(e)
            }
    
    async def run_comprehensive_test(self, campaign_data: Dict) -> Dict:
        """Run tests across all available services"""
        print("🧪 Running comprehensive spam and deliverability tests...")
        
        results = {
            'campaign_id': campaign_data.get('id'),
            'test_timestamp': datetime.now().isoformat(),
            'services': {},
            'overall_score': 0,
            'recommendations': [],
            'safe_to_send': False
        }
        
        # Test with Mail-Tester
        mail_tester_result = await self.test_with_mail_tester(
            campaign_data.get('html_content', ''),
            campaign_data.get('from_email', ''),
            campaign_data.get('subject', '')
        )
        results['services']['mail_tester'] = mail_tester_result
        
        # Test with GlockApps if available
        if self.glockapps_api_key:
            glockapps_result = await self.test_with_glockapps(campaign_data)
            results['services']['glockapps'] = glockapps_result
        
        # Test with Litmus if available
        if self.litmus_api_key:
            litmus_result = await self.test_with_litmus(campaign_data)
            results['services']['litmus'] = litmus_result
        
        # Calculate overall score
        scores = []
        if 'mail_tester' in results['services'] and 'score' in results['services']['mail_tester']:
            scores.append(results['services']['mail_tester']['percentage'])
        
        if 'glockapps' in results['services'] and 'inbox_rate' in results['services']['glockapps']:
            scores.append(results['services']['glockapps']['inbox_rate'])
        
        if scores:
            results['overall_score'] = sum(scores) / len(scores)
            results['safe_to_send'] = results['overall_score'] >= 80
        
        # Compile recommendations
        all_recommendations = []
        for service_result in results['services'].values():
            if 'recommendations' in service_result:
                all_recommendations.extend(service_result['recommendations'])
        
        results['recommendations'] = list(set(all_recommendations))  # Remove duplicates
        
        print(f"✅ Comprehensive test complete. Overall score: {results['overall_score']:.1f}%")
        return results
    
    def get_service_status(self) -> Dict:
        """Check which testing services are available"""
        return {
            'mail_tester': {
                'available': True,
                'description': 'Free spam score testing',
                'cost': 'Free'
            },
            'glockapps': {
                'available': bool(self.glockapps_api_key),
                'description': 'Comprehensive inbox placement testing',
                'cost': '$79/month',
                'setup_required': not bool(self.glockapps_api_key)
            },
            'litmus': {
                'available': bool(self.litmus_api_key),
                'description': 'Email rendering and spam testing',
                'cost': '$99/month',
                'setup_required': not bool(self.litmus_api_key)
            }
        }
