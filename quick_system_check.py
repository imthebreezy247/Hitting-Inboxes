#!/usr/bin/env python3
"""
Quick System Check - Verify critical components are working
"""

import asyncio
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def check_database():
    """Check if async database is working"""
    try:
        from src.database.async_models import get_async_db
        db = await get_async_db()
        print("✅ Database connection: OK")
        return True
    except Exception as e:
        print(f"❌ Database connection: FAILED - {str(e)}")
        return False

async def check_email_engine():
    """Check if email engine is working"""
    try:
        from src.core.email_engine import EmailDeliveryEngine
        from src.database.async_models import get_async_db
        
        db = await get_async_db()
        engine = EmailDeliveryEngine(db)
        print("✅ Email engine: OK")
        return True
    except Exception as e:
        print(f"❌ Email engine: FAILED - {str(e)}")
        return False

async def check_inbox_tester():
    """Check if inbox placement tester is working"""
    try:
        from src.core.inbox_placement_tester import InboxPlacementTester
        from src.database.async_models import get_async_db
        
        db = await get_async_db()
        tester = InboxPlacementTester(db)
        print(f"✅ Inbox placement tester: OK ({len(tester.seed_accounts)} seed accounts)")
        return True
    except Exception as e:
        print(f"❌ Inbox placement tester: FAILED - {str(e)}")
        return False

async def main():
    """Run system checks"""
    print("🔍 SYSTEM HEALTH CHECK")
    print("=" * 30)
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    checks = [
        ("Database", check_database),
        ("Email Engine", check_email_engine),
        ("Inbox Tester", check_inbox_tester)
    ]
    
    results = []
    for name, check_func in checks:
        print(f"🔍 Checking {name}...")
        result = await check_func()
        results.append(result)
        print()
    
    if all(results):
        print("🎉 ALL SYSTEMS OPERATIONAL!")
        print("✅ Ready to run real inbox placement test")
    else:
        print("⚠️ SOME SYSTEMS HAVE ISSUES")
        print("🔧 Fix the failed components before running placement test")

if __name__ == "__main__":
    asyncio.run(main())
