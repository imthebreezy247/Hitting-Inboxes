# tests/test_critical_fixes.py
import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock

# Import the modules we've fixed
from src.core.email_engine import EmailDeliveryEngine, EmailDeliveryResult, CampaignSendResult
from src.core.provider_manager import ProviderManager
from src.core.warming_system import IPWarmingSchedule
from src.core.error_handling import (
    ErrorHandler, EmailDeliveryError, ESPConnectionError, 
    RateLimitError, DatabaseError, ValidationError
)
from src.core.rate_limiter import TokenBucket, RateLimitManager, ESPRateLimiter
from src.database.async_models import AsyncDatabaseManager

class TestAsyncEmailEngine:
    """Test the async email delivery engine"""
    
    @pytest.fixture
    async def mock_db(self):
        """Mock async database"""
        db = Mock()
        db.get_campaign = AsyncMock(return_value={
            'id': 1,
            'name': 'Test Campaign',
            'subject': 'Test Subject',
            'html_content': '<html><body>Test</body></html>',
            'from_email': 'test@example.com'
        })
        db.get_campaign_subscribers = AsyncMock(return_value=[
            {'id': 1, 'email': 'user1@example.com', 'name': 'User 1'},
            {'id': 2, 'email': 'user2@example.com', 'name': 'User 2'}
        ])
        return db
    
    @pytest.mark.asyncio
    async def test_send_campaign_async(self, mock_db):
        """Test that send_campaign is properly async"""
        engine = EmailDeliveryEngine(mock_db)
        
        # This should not raise any errors about missing await
        result = await engine.send_campaign(1, warming_mode=False)
        
        assert isinstance(result, CampaignSendResult)
        assert result.campaign_id == 1
        assert result.total_recipients >= 0
        
    @pytest.mark.asyncio
    async def test_send_campaign_with_warming(self, mock_db):
        """Test campaign sending with warming mode"""
        engine = EmailDeliveryEngine(mock_db)
        
        result = await engine.send_campaign(1, warming_mode=True)
        
        assert isinstance(result, CampaignSendResult)
        assert result.campaign_id == 1

class TestProviderManager:
    """Test ESP provider management"""
    
    def test_provider_initialization(self):
        """Test provider manager initialization"""
        manager = ProviderManager(Mock())
        
        stats = manager.get_provider_stats()
        
        assert 'sendgrid' in stats
        assert 'amazon_ses' in stats
        assert 'postmark' in stats
        
        for provider, data in stats.items():
            assert 'can_send' in data
            assert 'reputation_score' in data
            assert 'daily_limit' in data
    
    def test_provider_selection(self):
        """Test best provider selection"""
        manager = ProviderManager(Mock())
        
        best_provider = manager.get_best_provider(email_count=10)
        
        assert best_provider in ['sendgrid', 'amazon_ses', 'postmark']
    
    def test_provider_failure_handling(self):
        """Test provider failure recording"""
        manager = ProviderManager(Mock())
        
        # Record multiple failures
        for _ in range(5):
            manager.record_send_failure('sendgrid', 'Connection timeout')
        
        stats = manager.get_provider_stats()
        assert stats['sendgrid']['failure_count'] == 5
    
    def test_health_check(self):
        """Test provider health check"""
        manager = ProviderManager(Mock())
        
        health = manager.get_provider_health_check()
        
        assert isinstance(health, dict)
        for provider_id, status in health.items():
            assert 'status' in status
            assert status['status'] in ['healthy', 'degraded', 'unhealthy']

class TestIPWarmingSchedule:
    """Test IP warming system"""
    
    def test_warming_schedule_initialization(self):
        """Test warming schedule setup"""
        warming = IPWarmingSchedule()
        
        assert 1 in warming.warming_schedule
        assert 30 in warming.warming_schedule
        
        day1_schedule = warming.warming_schedule[1]
        assert day1_schedule.max_emails == 50
        assert 'sendgrid' in day1_schedule.esp_limits
    
    def test_get_warming_status(self):
        """Test getting warming status"""
        warming = IPWarmingSchedule()
        
        status = warming.get_warming_status(Mock(), 'sendgrid')
        
        assert 'provider' in status
        assert 'status' in status
        assert 'warming_day' in status
        assert status['provider'] == 'sendgrid'
    
    def test_daily_sending_limit(self):
        """Test daily sending limit calculation"""
        warming = IPWarmingSchedule()
        
        day1_limit = warming.get_daily_sending_limit('sendgrid', 1)
        day30_limit = warming.get_daily_sending_limit('sendgrid', 30)
        
        assert day1_limit < day30_limit
        assert day1_limit == 20  # From warming schedule
        assert day30_limit == 4000

class TestErrorHandling:
    """Test error handling system"""
    
    def test_error_handler_initialization(self):
        """Test error handler setup"""
        handler = ErrorHandler()
        
        assert handler.error_counts == {}
        assert handler.circuit_breakers == {}
        assert len(handler.alert_thresholds) > 0
    
    def test_email_delivery_error_handling(self):
        """Test handling of EmailDeliveryError"""
        handler = ErrorHandler()
        
        error = EmailDeliveryError("Test error")
        result = handler.handle_error(error)
        
        assert 'error_id' in result
        assert 'category' in result
        assert 'severity' in result
        assert result['message'] == "Test error"
    
    def test_esp_connection_error_handling(self):
        """Test ESP connection error handling"""
        handler = ErrorHandler()
        
        error = ESPConnectionError("Connection failed", "sendgrid", 500, "Server Error")
        result = handler.handle_error(error)
        
        assert result['category'] == 'esp_connection'
        assert result['details']['esp_name'] == 'sendgrid'
        assert result['details']['status_code'] == 500
    
    def test_rate_limit_error_handling(self):
        """Test rate limit error handling"""
        handler = ErrorHandler()
        
        error = RateLimitError("Rate limit exceeded", "sendgrid", "hourly", 100, 80)
        result = handler.handle_error(error)
        
        assert result['category'] == 'rate_limiting'
        assert result['details']['esp_name'] == 'sendgrid'
        assert result['details']['current_count'] == 100
    
    def test_circuit_breaker_logic(self):
        """Test circuit breaker functionality"""
        handler = ErrorHandler()
        
        # Trigger multiple ESP connection errors
        for _ in range(6):
            error = ESPConnectionError("Connection failed", "sendgrid")
            handler.handle_error(error)
        
        assert 'sendgrid' in handler.circuit_breakers
        assert handler.circuit_breakers['sendgrid']['failure_count'] >= 5

class TestRateLimiting:
    """Test rate limiting system"""
    
    @pytest.mark.asyncio
    async def test_token_bucket_basic(self):
        """Test basic token bucket functionality"""
        bucket = TokenBucket(rate=1.0, capacity=10)
        
        # Should be able to consume tokens initially
        assert await bucket.consume(5) == True
        assert await bucket.consume(5) == True
        
        # Should fail when bucket is empty
        assert await bucket.consume(1) == False
    
    @pytest.mark.asyncio
    async def test_token_bucket_refill(self):
        """Test token bucket refill over time"""
        bucket = TokenBucket(rate=10.0, capacity=10)  # 10 tokens per second
        
        # Consume all tokens
        await bucket.consume(10)
        
        # Wait for refill
        await asyncio.sleep(0.5)  # Should refill ~5 tokens
        
        # Should be able to consume some tokens
        assert await bucket.consume(3) == True
    
    def test_esp_rate_limiter_initialization(self):
        """Test ESP rate limiter setup"""
        config = {
            'hourly_limit': 100,
            'daily_limit': 1000,
            'burst_limit': 50
        }
        
        limiter = ESPRateLimiter('sendgrid', config)
        
        assert limiter.esp_name == 'sendgrid'
        assert len(limiter.buckets) > 0
    
    @pytest.mark.asyncio
    async def test_esp_rate_limiter_can_send(self):
        """Test ESP rate limiter send checking"""
        config = {
            'hourly_limit': 100,
            'daily_limit': 1000,
            'burst_limit': 50
        }
        
        limiter = ESPRateLimiter('sendgrid', config)
        
        result = await limiter.can_send(10)
        
        assert 'can_send' in result
        assert 'esp_name' in result
        assert result['esp_name'] == 'sendgrid'
    
    def test_rate_limit_manager(self):
        """Test rate limit manager"""
        manager = RateLimitManager()
        
        # Should have default ESP limiters
        status = manager.get_all_status()
        
        assert 'esp_limiters' in status
        assert len(status['esp_limiters']) > 0

class TestAsyncDatabase:
    """Test async database operations"""
    
    @pytest.mark.asyncio
    async def test_database_initialization(self):
        """Test async database initialization"""
        db = AsyncDatabaseManager(":memory:")  # Use in-memory database for testing
        
        await db.initialize()
        
        assert db._initialized == True
        assert len(db._connection_pool) > 0
    
    @pytest.mark.asyncio
    async def test_database_query_execution(self):
        """Test async query execution"""
        db = AsyncDatabaseManager(":memory:")
        await db.initialize()
        
        # Test basic query
        results = await db.execute_query("SELECT 1 as test")
        
        assert len(results) == 1
        assert results[0]['test'] == 1
    
    @pytest.mark.asyncio
    async def test_database_update_execution(self):
        """Test async update execution"""
        db = AsyncDatabaseManager(":memory:")
        await db.initialize()
        
        # Test insert
        affected = await db.execute_update(
            "INSERT INTO subscribers (email, name) VALUES (?, ?)",
            ("test@example.com", "Test User")
        )
        
        assert affected == 1

class TestIntegration:
    """Integration tests for the complete system"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_campaign_send(self):
        """Test complete campaign sending flow"""
        # Mock database
        mock_db = Mock()
        mock_db.get_campaign_subscribers = AsyncMock(return_value=[
            {'id': 1, 'email': 'test@example.com', 'name': 'Test User'}
        ])
        
        # Initialize engine
        engine = EmailDeliveryEngine(mock_db)
        
        # Mock the internal methods to avoid actual email sending
        engine._get_campaign = AsyncMock(return_value={
            'id': 1, 'name': 'Test Campaign', 'subject': 'Test'
        })
        engine._get_campaign_subscribers = AsyncMock(return_value=[
            {'id': 1, 'email': 'test@example.com', 'name': 'Test User'}
        ])
        engine._send_batches_concurrently = AsyncMock(return_value=[
            EmailDeliveryResult(
                success=True, sent_count=1, failed_count=0,
                failed_emails=[], esp_used='sendgrid', message_ids=['msg1']
            )
        ])
        engine._update_campaign_status = AsyncMock()
        
        # Send campaign
        result = await engine.send_campaign(1, warming_mode=False)
        
        assert isinstance(result, CampaignSendResult)
        assert result.campaign_id == 1
        assert result.sent_count >= 0

# Test configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
