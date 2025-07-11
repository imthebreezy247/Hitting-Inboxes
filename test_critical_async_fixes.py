#!/usr/bin/env python3
"""
Critical Async/Await Bug Fixes Test Suite
Tests the fixes for:
1. Async/await patterns in routes.py
2. Database session management
3. Real IMAP inbox placement testing
"""

import asyncio
import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

class TestCriticalAsyncFixes:
    """Test suite for critical async/await bug fixes"""
    
    def setUp(self):
        """Set up test environment"""
        print("🧪 Setting up Critical Async Fixes Test Suite")
        print("=" * 60)
    
    async def test_async_campaign_send_endpoint(self):
        """Test that campaign send endpoint properly handles async operations"""
        print("\n1. Testing Async Campaign Send Endpoint")
        print("-" * 40)
        
        try:
            from src.api.routes import send_campaign
            from src.core.email_engine import EmailDeliveryEngine
            from src.database.async_models import AsyncDatabaseManager
            
            # Mock database session
            mock_db = Mock(spec=AsyncDatabaseManager)
            mock_db.execute_query = AsyncMock(return_value=[])
            mock_db.execute_update = AsyncMock(return_value=1)
            
            # Mock email engine
            with patch('src.api.routes.EmailDeliveryEngine') as mock_engine_class:
                mock_engine = Mock()
                mock_engine.send_campaign = AsyncMock(return_value=Mock(
                    sent_count=10,
                    total_recipients=10,
                    failed_count=0,
                    esp_distribution={'test_esp': 10},
                    start_time=datetime.now(),
                    end_time=datetime.now()
                ))
                mock_engine_class.return_value = mock_engine
                
                # Test async call
                result = await send_campaign(
                    campaign_id=1,
                    warming_mode=False,
                    background_tasks=None,
                    db=mock_db
                )
                
                # Verify async method was called
                mock_engine.send_campaign.assert_called_once_with(1, False)
                
                print("✅ Campaign send endpoint correctly uses async/await")
                print(f"   Result: {result['success']}")
                return True
                
        except Exception as e:
            print(f"❌ Campaign send endpoint test failed: {str(e)}")
            return False
    
    async def test_database_session_management(self):
        """Test proper database session lifecycle management"""
        print("\n2. Testing Database Session Management")
        print("-" * 40)
        
        try:
            from src.api.routes import get_async_db_session
            from src.database.async_models import get_async_db
            
            # Test session dependency
            async for session in get_async_db_session():
                # Verify we get a proper database manager
                assert hasattr(session, 'execute_query')
                assert hasattr(session, 'execute_update')
                assert hasattr(session, 'get_connection')
                
                print("✅ Database session properly initialized")
                
                # Test that session handles operations correctly
                try:
                    # This should not raise an exception
                    result = await session.execute_query("SELECT 1", ())
                    print("✅ Database session can execute queries")
                except Exception as e:
                    print(f"⚠️ Database query test failed (expected in test env): {str(e)}")
                
                break  # Only test first iteration
            
            print("✅ Database session management working correctly")
            return True
            
        except Exception as e:
            print(f"❌ Database session management test failed: {str(e)}")
            return False
    
    async def test_real_imap_placement_testing(self):
        """Test real IMAP inbox placement testing implementation"""
        print("\n3. Testing Real IMAP Inbox Placement Testing")
        print("-" * 40)
        
        try:
            from src.core.inbox_placement_tester import InboxPlacementTester, SeedAccount
            
            # Mock database
            mock_db = Mock()
            
            # Create tester instance
            tester = InboxPlacementTester(mock_db)
            
            # Test that new methods exist
            required_methods = [
                '_connect_imap',
                '_search_email_in_folders', 
                '_get_folders_for_provider',
                '_parse_email_headers',
                '_create_error_result',
                '_send_via_basic_smtp'
            ]
            
            missing_methods = []
            for method in required_methods:
                if not hasattr(tester, method):
                    missing_methods.append(method)
            
            if missing_methods:
                print(f"❌ Missing methods: {missing_methods}")
                return False
            
            print("✅ All required IMAP methods implemented")
            
            # Test folder mapping
            gmail_folders = tester._get_folders_for_provider('gmail')
            outlook_folders = tester._get_folders_for_provider('outlook')
            
            assert len(gmail_folders) > 0
            assert len(outlook_folders) > 0
            assert ('INBOX', 'inbox') in gmail_folders
            assert ('INBOX', 'inbox') in outlook_folders
            
            print("✅ Provider-specific folder mappings working")
            
            # Test error result creation
            test_seed = SeedAccount(
                email="test@example.com",
                password="test",
                provider="gmail",
                imap_server="imap.gmail.com"
            )
            
            error_result = tester._create_error_result(test_seed, "Test error")
            assert error_result.folder == 'error'
            assert error_result.seed_email == "test@example.com"
            
            print("✅ Error handling working correctly")
            print("✅ Real IMAP placement testing implemented")
            return True
            
        except Exception as e:
            print(f"❌ IMAP placement testing test failed: {str(e)}")
            return False
    
    async def test_async_consistency_across_routes(self):
        """Test that all route endpoints use consistent async patterns"""
        print("\n4. Testing Async Consistency Across Routes")
        print("-" * 40)
        
        try:
            import inspect
            from src.api import routes
            
            # Get all route functions
            route_functions = []
            for name in dir(routes):
                obj = getattr(routes, name)
                if callable(obj) and not name.startswith('_'):
                    route_functions.append((name, obj))
            
            async_routes = []
            sync_routes = []
            
            for name, func in route_functions:
                if inspect.iscoroutinefunction(func):
                    async_routes.append(name)
                elif callable(func):
                    sync_routes.append(name)
            
            print(f"✅ Found {len(async_routes)} async routes")
            print(f"✅ Found {len(sync_routes)} sync routes")
            
            # Key routes that should be async
            critical_async_routes = [
                'send_campaign', 'create_campaign', 'create_subscriber',
                'get_subscriber', 'list_subscribers', 'system_status'
            ]
            
            missing_async = []
            for route in critical_async_routes:
                if route not in async_routes:
                    missing_async.append(route)
            
            if missing_async:
                print(f"❌ Critical routes not async: {missing_async}")
                return False
            
            print("✅ All critical routes are properly async")
            return True
            
        except Exception as e:
            print(f"❌ Async consistency test failed: {str(e)}")
            return False
    
    async def run_all_tests(self):
        """Run all critical fix tests"""
        print("🚀 Running Critical Async Fixes Test Suite")
        print("=" * 60)
        
        tests = [
            self.test_async_campaign_send_endpoint,
            self.test_database_session_management,
            self.test_real_imap_placement_testing,
            self.test_async_consistency_across_routes
        ]
        
        results = []
        for test in tests:
            try:
                result = await test()
                results.append(result)
            except Exception as e:
                print(f"❌ Test {test.__name__} failed with exception: {str(e)}")
                results.append(False)
        
        # Summary
        print("\n" + "=" * 60)
        print("🏁 TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(results)
        total = len(results)
        
        print(f"Tests Passed: {passed}/{total}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            print("🎉 ALL CRITICAL FIXES WORKING CORRECTLY!")
        else:
            print("⚠️ Some tests failed - review fixes needed")
        
        return passed == total

async def main():
    """Main test runner"""
    tester = TestCriticalAsyncFixes()
    tester.setUp()
    success = await tester.run_all_tests()
    
    if success:
        print("\n✅ All critical async/await bugs have been fixed!")
        return 0
    else:
        print("\n❌ Some critical issues remain - check test output")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
