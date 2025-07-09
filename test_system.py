#!/usr/bin/env python3
# test_system.py - Test script for Phase 1 implementation

import os
import sys
from datetime import datetime

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_database():
    """Test database initialization"""
    print("Testing database initialization...")
    try:
        from database.models import db
        
        # Test basic database operations
        test_subscriber = {
            'email': 'test@example.com',
            'name': 'Test User',
            'company': 'Test Company'
        }
        
        # Add test subscriber
        db.execute_update('''
            INSERT OR REPLACE INTO subscribers (email, name, company, status)
            VALUES (?, ?, ?, 'active')
        ''', (test_subscriber['email'], test_subscriber['name'], test_subscriber['company']))
        
        # Retrieve test subscriber
        result = db.execute_query('''
            SELECT * FROM subscribers WHERE email = ?
        ''', (test_subscriber['email'],))
        
        if result:
            print("✓ Database operations working correctly")
            return True
        else:
            print("✗ Database test failed")
            return False
            
    except Exception as e:
        print(f"✗ Database error: {e}")
        return False

def test_esp_config():
    """Test ESP configuration"""
    print("Testing ESP configuration...")
    try:
        from config.esp_config import ESPConfigManager
        
        config_manager = ESPConfigManager()
        available_esps = config_manager.get_available_esps()
        
        print(f"Available ESPs: {len(available_esps)}")
        for esp in available_esps:
            print(f"  - {esp.provider.value}: Priority {esp.priority}, Daily limit {esp.daily_limit}")
        
        if available_esps:
            print("✓ ESP configuration loaded successfully")
            return True
        else:
            print("⚠ No ESPs configured (check .env file)")
            return False
            
    except Exception as e:
        print(f"✗ ESP configuration error: {e}")
        return False

def test_subscriber_manager():
    """Test subscriber management"""
    print("Testing subscriber management...")
    try:
        from list_manager import SubscriberManager
        
        manager = SubscriberManager(migrate_from_json=False)
        
        # Test adding subscriber
        success = manager.add_subscriber(
            'test2@example.com',
            'Test User 2',
            'Test Company 2',
            'test_script'
        )
        
        if success:
            # Test getting clean list
            clean_list = manager.clean_list()
            print(f"Clean subscriber list: {len(clean_list)} subscribers")
            
            # Test stats
            stats = manager.get_subscriber_stats()
            print(f"Subscriber stats: {stats}")
            
            print("✓ Subscriber management working correctly")
            return True
        else:
            print("✗ Failed to add test subscriber")
            return False
            
    except Exception as e:
        print(f"✗ Subscriber management error: {e}")
        return False

def test_dns_checker():
    """Test DNS checker"""
    print("Testing DNS checker...")
    try:
        from utils.dns_checker import DNSChecker
        
        dns_checker = DNSChecker()
        
        # Test loading configuration
        if dns_checker.domain_config:
            print(f"✓ Domain configuration loaded for {dns_checker.domain_config.get('primary_domain', 'unknown')}")
            
            # Generate instructions
            instructions = dns_checker.generate_dns_setup_instructions()
            if instructions:
                print("✓ DNS setup instructions generated")
                return True
            else:
                print("✗ Failed to generate DNS instructions")
                return False
        else:
            print("✗ Failed to load domain configuration")
            return False
            
    except Exception as e:
        print(f"✗ DNS checker error: {e}")
        return False

def test_email_system():
    """Test email system initialization"""
    print("Testing email system...")
    try:
        from email_sender import EmailDeliverySystem
        
        email_system = EmailDeliverySystem()
        
        # Test ESP status
        esp_status = email_system.get_esp_status()
        print(f"ESP status: {len(esp_status)} providers configured")
        
        # Test optimal ESP selection
        optimal_esp = email_system.get_optimal_esp(1)
        if optimal_esp:
            print(f"✓ Optimal ESP for sending: {optimal_esp}")
        else:
            print("⚠ No optimal ESP available (check API keys)")
        
        print("✓ Email system initialized successfully")
        return True
        
    except Exception as e:
        print(f"✗ Email system error: {e}")
        return False

def main():
    """Run all tests"""
    print("=== Email Delivery System - Phase 1 Tests ===")
    print(f"Test started at: {datetime.now()}")
    print("")
    
    tests = [
        test_database,
        test_esp_config,
        test_subscriber_manager,
        test_dns_checker,
        test_email_system
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
        print("")
    
    print("=== Test Results ===")
    print(f"Passed: {passed}/{total}")
    print(f"Success rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 All tests passed! System is ready for Phase 2.")
    elif passed >= total * 0.8:
        print("⚠ Most tests passed. Check warnings above.")
    else:
        print("❌ Multiple test failures. Check configuration and dependencies.")
    
    print("")
    print("Next steps:")
    print("1. Update .env file with real API keys")
    print("2. Configure DNS records")
    print("3. Run: python3 app.py to start the server")
    print("4. Ready for Phase 2 implementation!")

if __name__ == '__main__':
    main()
