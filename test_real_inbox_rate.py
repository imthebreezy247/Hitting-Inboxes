#!/usr/bin/env python3
"""
Real Inbox Placement Rate Test
Tests actual inbox placement using real IMAP connections instead of simulated results
"""

import asyncio
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.inbox_placement_tester import InboxPlacementTester
from src.database.async_models import get_async_db

async def test_real_placement():
    """Test real inbox placement rate with actual IMAP connections"""
    print("🎯 REAL INBOX PLACEMENT TEST")
    print("=" * 50)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        # Initialize database
        db = await get_async_db()
        print("✅ Database connection established")
        
        # Initialize inbox placement tester
        tester = InboxPlacementTester(db)
        print("✅ Inbox placement tester initialized")
        print(f"📧 Testing with {len(tester.seed_accounts)} seed accounts")
        print()
        
        # Create test content
        test_content = {
            'subject': f'Real Placement Test - {datetime.now().strftime("%Y-%m-%d %H:%M")}',
            'html_content': '''
            <html>
            <body>
                <h1>Real Inbox Placement Test</h1>
                <p>This is a test to determine actual inbox placement rates.</p>
                <p>Testing real IMAP connections instead of simulated results.</p>
                <p>Timestamp: {timestamp}</p>
            </body>
            </html>
            '''.format(timestamp=datetime.now().isoformat()),
            'text_content': f'''
Real Inbox Placement Test

This is a test to determine actual inbox placement rates.
Testing real IMAP connections instead of simulated results.

Timestamp: {datetime.now().isoformat()}
            ''',
            'from_email': 'test@mail.cjsinsurancesolutions.com'
        }
        
        print("📧 Test email content prepared")
        print(f"📋 Subject: {test_content['subject']}")
        print()
        
        # Run placement test with campaign ID 1 (or create a test campaign)
        print("🚀 Running real inbox placement test...")
        print("⏳ This may take 2-3 minutes to complete...")
        print()
        
        results = await tester.test_campaign_placement(
            campaign_id=1,  # Use your latest campaign or test campaign
            content=test_content
        )
        
        # Display results
        print("📊 REAL INBOX PLACEMENT RESULTS")
        print("=" * 50)
        print(f"🎯 Overall Inbox Rate: {results['inbox_rate']:.1f}%")
        print(f"📧 Total Tested: {results['total_tested']}")
        print()
        
        print("📈 Breakdown by Provider:")
        for provider, stats in results.get('by_provider', {}).items():
            print(f"  📱 {provider.upper()}:")
            print(f"    ✅ Inbox: {stats.get('inbox_rate', 0):.1f}%")
            print(f"    📁 Promotions: {stats.get('promotions_rate', 0):.1f}%")
            print(f"    🚫 Spam: {stats.get('spam_rate', 0):.1f}%")
            print(f"    ❌ Not Delivered: {stats.get('not_delivered_rate', 0):.1f}%")
            print()
        
        # Provide recommendations based on results
        print("💡 RECOMMENDATIONS:")
        print("-" * 30)
        
        if results['inbox_rate'] >= 85:
            print("🟢 EXCELLENT: Your inbox placement is very good!")
        elif results['inbox_rate'] >= 75:
            print("🟡 GOOD: Your inbox placement is acceptable but can be improved")
            print("   • Focus on engagement and list hygiene")
            print("   • Consider warming up additional IPs")
        elif results['inbox_rate'] >= 60:
            print("🟠 NEEDS IMPROVEMENT: Your inbox placement needs attention")
            print("   • Review your authentication (SPF, DKIM, DMARC)")
            print("   • Improve content quality and reduce spam triggers")
            print("   • Implement proper IP warming")
        else:
            print("🔴 CRITICAL: Your inbox placement is very poor!")
            print("   • STOP sending immediately")
            print("   • Review all authentication settings")
            print("   • Clean your email list")
            print("   • Consider using a different sending domain")
        
        print()
        print("🔍 NEXT STEPS:")
        print("1. Compare this to your previous simulated 98% rate")
        print("2. If significantly lower, focus on authentication and warming")
        print("3. Run this test weekly to monitor improvements")
        print("4. Implement webhook processing for real-time tracking")
        
        return results
        
    except Exception as e:
        print(f"❌ Error during inbox placement test: {str(e)}")
        print("🔧 Troubleshooting:")
        print("   • Check that seed accounts are properly configured")
        print("   • Verify IMAP credentials are correct")
        print("   • Ensure email sending is working")
        return None

async def main():
    """Main function to run the test"""
    print("🚀 Starting Real Inbox Placement Rate Test")
    print()
    
    results = await test_real_placement()
    
    if results:
        print()
        print("✅ Test completed successfully!")
        print(f"📊 Your REAL inbox placement rate: {results['inbox_rate']:.1f}%")
        
        # Save results to file for reference
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"inbox_placement_results_{timestamp}.json"
        
        import json
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"💾 Results saved to: {filename}")
    else:
        print("❌ Test failed - check configuration and try again")

if __name__ == "__main__":
    asyncio.run(main())
