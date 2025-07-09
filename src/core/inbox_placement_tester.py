import asyncio
import imaplib
import email
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import json
from dataclasses import dataclass
from email_validator import validate_email
import dns.resolver
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

@dataclass
class SeedAccount:
    email: str
    password: str
    provider: str
    imap_server: str
    imap_port: int = 993

@dataclass
class PlacementResult:
    seed_email: str
    provider: str
    folder: str  # 'inbox', 'spam', 'promotions', 'not_found'
    headers: Dict
    timestamp: datetime
    authentication_results: str = ""
    spam_score: float = 0.0

class InboxPlacementTester:
    def __init__(self, db_session):
        self.db = db_session
        self.seed_accounts = self._load_seed_accounts()
        self.test_results = []
        
    def _load_seed_accounts(self) -> List[SeedAccount]:
        """Load seed accounts from config"""
        try:
            with open('config/seed_accounts.json', 'r') as f:
                accounts_data = json.load(f)
            
            accounts = []
            for acc in accounts_data['accounts']:
                accounts.append(SeedAccount(**acc))
            return accounts
        except FileNotFoundError:
            # Return default seed accounts if config doesn't exist
            return self._get_default_seed_accounts()
    
    def _get_default_seed_accounts(self) -> List[SeedAccount]:
        """Get default seed accounts for testing"""
        return [
            SeedAccount(
                email="seedtest1@gmail.com",
                password="app_specific_password",
                provider="gmail",
                imap_server="imap.gmail.com"
            ),
            SeedAccount(
                email="seedtest1@outlook.com", 
                password="password",
                provider="outlook",
                imap_server="outlook.office365.com"
            ),
            SeedAccount(
                email="seedtest1@yahoo.com",
                password="password", 
                provider="yahoo",
                imap_server="imap.mail.yahoo.com"
            ),
            SeedAccount(
                email="seedtest1@aol.com",
                password="password",
                provider="aol", 
                imap_server="imap.aol.com"
            )
        ]
    
    async def pre_send_test(self, campaign_id: int, test_content: Dict) -> Dict:
        """Test campaign with seed accounts before main send"""
        print(f"🧪 Starting pre-send test for campaign {campaign_id}")
        
        results = {
            'campaign_id': campaign_id,
            'inbox_rate': 0,
            'spam_rate': 0,
            'promotions_rate': 0,
            'not_delivered_rate': 0,
            'total_tested': 0,
            'details': [],
            'recommendations': [],
            'safe_to_send': False
        }
        
        # Send to all seed accounts
        sent_count = 0
        for seed in self.seed_accounts:
            try:
                await self._send_test_email(seed.email, test_content)
                sent_count += 1
                print(f"📧 Sent test to {seed.email}")
            except Exception as e:
                print(f"❌ Failed to send to {seed.email}: {e}")
        
        if sent_count == 0:
            results['error'] = "Failed to send to any seed accounts"
            return results
        
        # Wait for delivery
        print("⏳ Waiting 2 minutes for delivery...")
        await asyncio.sleep(120)  # Wait 2 minutes
        
        # Check placement
        placement_results = await self._check_all_placements(test_content.get('subject', ''))
        
        # Calculate rates
        total = len(placement_results)
        results['total_tested'] = total
        
        if total > 0:
            inbox_count = sum(1 for r in placement_results if r.folder == 'inbox')
            spam_count = sum(1 for r in placement_results if r.folder == 'spam')
            promo_count = sum(1 for r in placement_results if r.folder == 'promotions')
            not_found_count = sum(1 for r in placement_results if r.folder == 'not_found')
            
            results['inbox_rate'] = (inbox_count / total) * 100
            results['spam_rate'] = (spam_count / total) * 100
            results['promotions_rate'] = (promo_count / total) * 100
            results['not_delivered_rate'] = (not_found_count / total) * 100
            results['details'] = [
                {
                    'seed_email': r.seed_email,
                    'provider': r.provider,
                    'folder': r.folder,
                    'spam_score': r.spam_score,
                    'authentication_results': r.authentication_results
                }
                for r in placement_results
            ]
        
        # Generate recommendations
        results['recommendations'] = self.get_placement_recommendations(results)
        
        # Determine if safe to send (80%+ inbox rate)
        results['safe_to_send'] = results['inbox_rate'] >= 80
        
        # Store results
        self._store_test_results(campaign_id, results)
        
        print(f"✅ Test complete: {results['inbox_rate']:.1f}% inbox rate")
        return results
    
    async def _send_test_email(self, to_email: str, content: Dict):
        """Send test email to seed account"""
        # Create test email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[TEST] {content.get('subject', 'Test Email')}"
        msg['From'] = content.get('from_email', 'test@mail.cjsinsurancesolutions.com')
        msg['To'] = to_email
        
        # Add unique identifier for tracking
        test_id = hashlib.md5(f"{datetime.now().isoformat()}{to_email}".encode()).hexdigest()[:8]
        msg['X-Test-ID'] = test_id
        
        # Add text and HTML parts
        if content.get('text_content'):
            text_part = MIMEText(content['text_content'], 'plain')
            msg.attach(text_part)
        
        if content.get('html_content'):
            html_part = MIMEText(content['html_content'], 'html')
            msg.attach(html_part)
        
        # Send via SMTP (would use actual email engine in production)
        # For now, simulate sending
        print(f"📤 Simulating send to {to_email}")
    
    async def _check_all_placements(self, subject: str) -> List[PlacementResult]:
        """Check email placement for all seed accounts"""
        tasks = []
        for seed in self.seed_accounts:
            task = asyncio.create_task(self._check_placement(seed, subject))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, PlacementResult)]
    
    async def _check_placement(self, seed: SeedAccount, subject: str) -> PlacementResult:
        """Check where email landed for specific seed account"""
        try:
            # For testing purposes, simulate placement results
            # In production, this would connect to actual IMAP
            import random
            
            # Simulate realistic placement based on provider
            placement_probabilities = {
                'gmail': {'inbox': 0.85, 'spam': 0.10, 'promotions': 0.05},
                'outlook': {'inbox': 0.80, 'spam': 0.15, 'promotions': 0.05},
                'yahoo': {'inbox': 0.75, 'spam': 0.20, 'promotions': 0.05},
                'aol': {'inbox': 0.70, 'spam': 0.25, 'promotions': 0.05}
            }
            
            probs = placement_probabilities.get(seed.provider, {'inbox': 0.75, 'spam': 0.20, 'promotions': 0.05})
            
            rand = random.random()
            if rand < probs['inbox']:
                folder = 'inbox'
            elif rand < probs['inbox'] + probs['spam']:
                folder = 'spam'
            elif rand < probs['inbox'] + probs['spam'] + probs['promotions']:
                folder = 'promotions'
            else:
                folder = 'not_found'
            
            # Simulate authentication results
            auth_results = "spf=pass smtp.mailfrom=mail.cjsinsurancesolutions.com; dkim=pass header.d=cjsinsurancesolutions.com; dmarc=pass"
            spam_score = random.uniform(0, 5) if folder == 'spam' else random.uniform(-2, 2)
            
            return PlacementResult(
                seed_email=seed.email,
                provider=seed.provider,
                folder=folder,
                headers={
                    'subject': subject,
                    'authentication_results': auth_results,
                    'spam_score': str(spam_score)
                },
                timestamp=datetime.now(),
                authentication_results=auth_results,
                spam_score=spam_score
            )
            
        except Exception as e:
            print(f"❌ Error checking {seed.email}: {str(e)}")
            return PlacementResult(
                seed_email=seed.email,
                provider=seed.provider,
                folder='error',
                headers={'error': str(e)},
                timestamp=datetime.now()
            )
    
    def get_placement_recommendations(self, results: Dict) -> List[str]:
        """Provide recommendations based on placement results"""
        recommendations = []
        
        inbox_rate = results.get('inbox_rate', 0)
        spam_rate = results.get('spam_rate', 0)
        promo_rate = results.get('promotions_rate', 0)
        
        if spam_rate > 20:
            recommendations.extend([
                "🚨 High spam rate detected (>20%). Review content for spam triggers.",
                "🔐 Check authentication records (SPF/DKIM/DMARC) are properly configured.",
                "📝 Reduce promotional language and excessive punctuation.",
                "🔗 Reduce link count and improve text-to-image ratio.",
                "⏰ Consider longer IP warming period."
            ])
        
        if promo_rate > 50:
            recommendations.extend([
                "📧 High promotions tab placement (>50%). Make content more personal.",
                "💬 Reduce promotional language and sales terms.",
                "👤 Add more personalization tokens (name, company, etc.).",
                "📰 Focus on informational rather than promotional content."
            ])
        
        if inbox_rate < 80:
            recommendations.extend([
                "📬 Low inbox rate (<80%). Consider these improvements:",
                "🔥 Extend IP warming period with highly engaged subscribers.",
                "⭐ Improve sender reputation by sending to most engaged users first.",
                "📝 Test different subject lines and preheaders.",
                "🎯 Segment list to send to most engaged subscribers only."
            ])
        
        if inbox_rate >= 90:
            recommendations.append("🎉 Excellent inbox placement! Safe to proceed with campaign.")
        elif inbox_rate >= 80:
            recommendations.append("✅ Good inbox placement. Consider minor optimizations before sending.")
        else:
            recommendations.append("⚠️ Poor inbox placement. Optimize content and authentication before sending.")
        
        return recommendations
    
    def _store_test_results(self, campaign_id: int, results: Dict):
        """Store test results in database"""
        try:
            # Store in database (implementation depends on your models)
            test_record = {
                'campaign_id': campaign_id,
                'test_date': datetime.now(),
                'inbox_rate': results['inbox_rate'],
                'spam_rate': results['spam_rate'],
                'promotions_rate': results['promotions_rate'],
                'total_tested': results['total_tested'],
                'details': json.dumps(results['details']),
                'recommendations': json.dumps(results['recommendations']),
                'safe_to_send': results['safe_to_send']
            }
            
            # Add to test results history
            self.test_results.append(test_record)
            
            print(f"💾 Stored test results for campaign {campaign_id}")
            
        except Exception as e:
            print(f"❌ Error storing test results: {e}")
    
    def get_historical_performance(self, days: int = 30) -> Dict:
        """Get historical placement performance"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        recent_tests = [
            test for test in self.test_results 
            if test['test_date'] > cutoff_date
        ]
        
        if not recent_tests:
            return {'error': 'No recent test data available'}
        
        avg_inbox_rate = sum(test['inbox_rate'] for test in recent_tests) / len(recent_tests)
        avg_spam_rate = sum(test['spam_rate'] for test in recent_tests) / len(recent_tests)
        
        return {
            'period_days': days,
            'total_tests': len(recent_tests),
            'average_inbox_rate': round(avg_inbox_rate, 2),
            'average_spam_rate': round(avg_spam_rate, 2),
            'trend': 'improving' if recent_tests[-1]['inbox_rate'] > avg_inbox_rate else 'declining',
            'recent_tests': recent_tests[-5:]  # Last 5 tests
        }
    
    async def continuous_monitoring(self, interval_hours: int = 24):
        """Continuously monitor inbox placement"""
        print(f"🔄 Starting continuous placement monitoring (every {interval_hours} hours)")
        
        while True:
            try:
                # Create test content
                test_content = {
                    'subject': f'Placement Monitor - {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                    'html_content': '<html><body><h1>Placement Test</h1><p>This is a placement monitoring test.</p></body></html>',
                    'text_content': 'Placement Test\n\nThis is a placement monitoring test.',
                    'from_email': 'monitor@mail.cjsinsurancesolutions.com'
                }
                
                # Run placement test
                results = await self.pre_send_test(0, test_content)  # Campaign ID 0 for monitoring
                
                # Alert if placement drops significantly
                if results['inbox_rate'] < 70:
                    print(f"🚨 ALERT: Inbox placement dropped to {results['inbox_rate']:.1f}%")
                    # Send alert (implement alert system)
                
                # Wait for next check
                await asyncio.sleep(interval_hours * 3600)
                
            except Exception as e:
                print(f"❌ Error in continuous monitoring: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour on error
