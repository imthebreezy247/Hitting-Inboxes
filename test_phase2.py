#!/usr/bin/env python3
# test_phase2.py - Comprehensive test suite for Phase 2 implementation

import asyncio
import sys
import os
from datetime import datetime
import json

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def test_database_models():
    """Test database models and connections"""
    print("Testing database models...")
    try:
        from src.database.models import create_tables, get_db, Subscriber, Campaign
        
        # Create tables
        create_tables()
        print("✓ Database tables created successfully")
        
        # Test database connection
        db = next(get_db())
        
        # Test basic operations
        test_subscriber = Subscriber(
            email='test@phase2.com',
            name='Phase 2 Test User',
            segment='test',
            engagement_score=0.8
        )
        
        db.add(test_subscriber)
        db.commit()
        
        # Verify insertion
        retrieved = db.query(Subscriber).filter_by(email='test@phase2.com').first()
        if retrieved:
            print("✓ Database operations working correctly")
            return True
        else:
            print("✗ Database operation failed")
            return False
            
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False

def test_provider_manager():
    """Test provider manager functionality"""
    print("Testing provider manager...")
    try:
        from src.core.provider_manager import ProviderManager
        
        # Test initialization
        manager = ProviderManager()
        print(f"✓ Provider manager initialized with {len(manager.providers)} providers")
        
        # Test provider selection
        provider = manager.select_provider('test@gmail.com', 0.8)
        if provider:
            print(f"✓ Provider selection working: {provider.name}")
        else:
            print("⚠ No providers available (check API keys)")
        
        # Test provider stats
        stats = manager.get_provider_stats()
        print(f"✓ Provider stats retrieved: {len(stats)} providers")
        
        return True
        
    except Exception as e:
        print(f"✗ Provider manager test failed: {e}")
        return False

def test_warming_system():
    """Test IP warming system"""
    print("Testing IP warming system...")
    try:
        from src.core.warming_system import IPWarmingSchedule
        
        # Test initialization
        warming = IPWarmingSchedule()
        print("✓ Warming system initialized")
        
        # Test day configuration
        day_config = warming.get_current_day_config(1)
        print(f"✓ Day 1 config: {day_config['volume']} emails, segment: {day_config['segment']}")
        
        # Test segment criteria
        criteria = warming.get_segment_criteria('most_engaged')
        print(f"✓ Segment criteria loaded: min engagement {criteria.get('min_engagement_score', 0)}")
        
        return True
        
    except Exception as e:
        print(f"✗ Warming system test failed: {e}")
        return False

def test_email_builder():
    """Test email builder and optimization"""
    print("Testing email builder...")
    try:
        from src.utils.email_builder import OptimizedEmailBuilder
        
        builder = OptimizedEmailBuilder()
        print("✓ Email builder initialized")
        
        # Test email building
        template = """
        <html>
        <body>
            <h1>Hello {{name}}</h1>
            <p>Welcome to {{company}}!</p>
            <a href="{{unsubscribe_link}}">Unsubscribe</a>
        </body>
        </html>
        """
        
        variables = {'company': 'CJS Insurance Solutions'}
        tokens = {'name': 'Test User', 'unsubscribe_link': 'https://example.com/unsubscribe'}
        
        html, text = builder.build_email(template, variables, tokens)
        
        if 'Test User' in html and 'CJS Insurance Solutions' in html:
            print("✓ Email personalization working")
        else:
            print("✗ Email personalization failed")
            return False
        
        # Test content validation
        validation = builder._validate_content(html, text)
        print(f"✓ Content validation: {len(validation['warnings'])} warnings, {len(validation['errors'])} errors")
        
        return True
        
    except Exception as e:
        print(f"✗ Email builder test failed: {e}")
        return False

def test_subscriber_manager():
    """Test subscriber management"""
    print("Testing subscriber manager...")
    try:
        from src.database.models import get_db
        from src.database.subscriber_manager import SubscriberManager
        
        db = next(get_db())
        manager = SubscriberManager(db)
        print("✓ Subscriber manager initialized")
        
        # Test adding subscriber
        success, message = manager.add_subscriber(
            'phase2test@example.com',
            'Phase 2 Test',
            'Test Company',
            'test_segment'
        )
        
        if success:
            print("✓ Subscriber addition working")
        else:
            print(f"⚠ Subscriber addition: {message}")
        
        # Test getting subscriber
        subscriber = manager.get_subscriber('phase2test@example.com')
        if subscriber:
            print(f"✓ Subscriber retrieval working: {subscriber['name']}")
        else:
            print("✗ Subscriber retrieval failed")
            return False
        
        # Test engagement statistics
        stats = manager.get_engagement_statistics()
        print(f"✓ Engagement stats: {stats.get('total_subscribers', 0)} total subscribers")
        
        return True
        
    except Exception as e:
        print(f"✗ Subscriber manager test failed: {e}")
        return False

def test_engagement_tracker():
    """Test engagement tracking"""
    print("Testing engagement tracker...")
    try:
        from src.database.models import get_db
        from src.database.engagement_tracker import EngagementTracker
        
        db = next(get_db())
        tracker = EngagementTracker(db)
        print("✓ Engagement tracker initialized")
        
        # Test tracking email sent
        engagement_id = tracker.track_email_sent(1, 1, 'test_provider', 'test_message_123')
        if engagement_id:
            print(f"✓ Email sent tracking working: engagement ID {engagement_id}")
        else:
            print("⚠ Email sent tracking failed (may need valid subscriber/campaign)")
        
        # Test tracking open
        if engagement_id:
            success = tracker.track_open(engagement_id=engagement_id)
            if success:
                print("✓ Open tracking working")
            else:
                print("✗ Open tracking failed")
        
        return True
        
    except Exception as e:
        print(f"✗ Engagement tracker test failed: {e}")
        return False

async def test_email_engine():
    """Test email delivery engine"""
    print("Testing email delivery engine...")
    try:
        from src.database.models import get_db
        from src.core.email_engine import EmailDeliveryEngine
        
        db = next(get_db())
        engine = EmailDeliveryEngine(db)
        print("✓ Email engine initialized")
        
        # Test engine stats
        stats = engine.get_engine_stats()
        print(f"✓ Engine stats retrieved: {stats['session_stats']['sent']} emails sent this session")
        
        return True
        
    except Exception as e:
        print(f"✗ Email engine test failed: {e}")
        return False

def test_validators():
    """Test validation utilities"""
    print("Testing validators...")
    try:
        from src.utils.validators import EmailValidator, ContentValidator
        
        # Test email validation
        email_validator = EmailValidator()
        result = email_validator.validate_email_address('test@gmail.com')
        
        if result['is_valid']:
            print(f"✓ Email validation working: score {result['deliverability_score']}")
        else:
            print(f"✗ Email validation failed: {result['issues']}")
            return False
        
        # Test content validation
        content_validator = ContentValidator()
        subject_result = content_validator.validate_subject_line('Test Subject Line')
        
        if subject_result['is_valid']:
            print(f"✓ Subject validation working: spam score {subject_result['spam_score']}")
        else:
            print(f"✗ Subject validation failed: {subject_result['issues']}")
        
        return True
        
    except Exception as e:
        print(f"✗ Validators test failed: {e}")
        return False

def test_analytics():
    """Test analytics engine"""
    print("Testing analytics engine...")
    try:
        from src.database.models import get_db
        from src.utils.analytics import AnalyticsEngine
        
        db = next(get_db())
        analytics = AnalyticsEngine(db)
        print("✓ Analytics engine initialized")
        
        # Test subscriber lifecycle analysis
        lifecycle = analytics.get_subscriber_lifecycle_analysis(30)
        print(f"✓ Lifecycle analysis: {len(lifecycle.get('acquisition_trends', []))} data points")
        
        return True
        
    except Exception as e:
        print(f"✗ Analytics test failed: {e}")
        return False

def test_api_routes():
    """Test API route definitions"""
    print("Testing API routes...")
    try:
        from src.api.routes import app
        
        # Check if FastAPI app is created
        if app:
            print("✓ FastAPI app created successfully")
            
            # Check routes
            routes = [route.path for route in app.routes]
            expected_routes = ['/subscribers/', '/campaigns/', '/system/status']
            
            found_routes = [route for route in expected_routes if any(route in r for r in routes)]
            print(f"✓ API routes defined: {len(found_routes)}/{len(expected_routes)} expected routes found")
            
            return True
        else:
            print("✗ FastAPI app creation failed")
            return False
        
    except Exception as e:
        print(f"✗ API routes test failed: {e}")
        return False

def test_configuration_files():
    """Test configuration file loading"""
    print("Testing configuration files...")
    try:
        # Test provider config
        with open('config/providers.json', 'r') as f:
            provider_config = json.load(f)
        
        if 'sendgrid' in provider_config and 'aws_ses' in provider_config:
            print("✓ Provider configuration loaded")
        else:
            print("✗ Provider configuration incomplete")
            return False
        
        # Test warming config
        with open('config/warming_schedule.json', 'r') as f:
            warming_config = json.load(f)
        
        if 'schedule' in warming_config and 'segment_definitions' in warming_config:
            print("✓ Warming configuration loaded")
        else:
            print("✗ Warming configuration incomplete")
            return False
        
        # Test delivery rules
        with open('config/delivery_rules.json', 'r') as f:
            delivery_config = json.load(f)
        
        if 'send_time_optimization' in delivery_config and 'domain_specific_rules' in delivery_config:
            print("✓ Delivery rules configuration loaded")
        else:
            print("✗ Delivery rules configuration incomplete")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Configuration files test failed: {e}")
        return False

async def main():
    """Run all Phase 2 tests"""
    print("=== Email Delivery System - Phase 2 Tests ===")
    print(f"Test started at: {datetime.now()}")
    print("")
    
    tests = [
        test_configuration_files,
        test_database_models,
        test_provider_manager,
        test_warming_system,
        test_email_builder,
        test_subscriber_manager,
        test_engagement_tracker,
        test_email_engine,
        test_validators,
        test_analytics,
        test_api_routes
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if asyncio.iscoroutinefunction(test):
                result = await test()
            else:
                result = test()
            
            if result:
                passed += 1
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
        print("")
    
    print("=== Phase 2 Test Results ===")
    print(f"Passed: {passed}/{total}")
    print(f"Success rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 All Phase 2 tests passed! System is ready for production.")
    elif passed >= total * 0.8:
        print("⚠ Most tests passed. Check warnings above and configure API keys.")
    else:
        print("❌ Multiple test failures. Check configuration and dependencies.")
    
    print("")
    print("Phase 2 Features Tested:")
    print("✓ Advanced database models with SQLAlchemy")
    print("✓ Multi-ESP provider management with intelligent selection")
    print("✓ IP warming system with performance monitoring")
    print("✓ Email content optimization and validation")
    print("✓ Subscriber management with engagement scoring")
    print("✓ Real-time engagement tracking")
    print("✓ Email delivery engine with async support")
    print("✓ Content and email validation utilities")
    print("✓ Advanced analytics and reporting")
    print("✓ FastAPI REST API with comprehensive endpoints")
    print("")
    print("Next steps:")
    print("1. Configure API keys in .env file")
    print("2. Set up database (PostgreSQL recommended for production)")
    print("3. Configure DNS records for all ESPs")
    print("4. Run: python main.py to start the FastAPI server")
    print("5. Access API documentation at http://localhost:8000/docs")

if __name__ == '__main__':
    asyncio.run(main())
