# src/api/routes_clean.py
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from typing import List, Dict, Optional, Any
from datetime import datetime
import asyncio
import logging
import json

from ..database.models import get_db, create_tables
from ..database.async_models import get_async_db
from ..database.subscriber_manager import SubscriberManager
from ..database.engagement_tracker import EngagementTracker
from ..core.email_engine import EmailDeliveryEngine
from ..core.warming_system import IPWarmingSchedule
from ..core.provider_manager import ProviderManager
from ..core.error_handling import handle_error, ValidationError, EmailDeliveryError
from ..core.rate_limiter import rate_limit_manager
from .webhooks import webhook_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Email Delivery System API",
    description="Advanced email delivery system with multi-ESP support, warming, and analytics",
    version="2.0.0"
)

# Include webhook router
app.include_router(webhook_router)

# Pydantic models for request/response
class SubscriberCreate(BaseModel):
    email: EmailStr
    name: str
    company: Optional[str] = None
    segment: str = "general"
    source: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None

class SubscriberUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    segment: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None

class CampaignCreate(BaseModel):
    name: str
    subject: str
    html_content: str
    text_content: Optional[str] = None
    from_name: str = "Chris - CJS Insurance Solutions"
    from_email: str = "chris@mail.cjsinsurancesolutions.com"
    segment_rules: Optional[Dict[str, Any]] = None
    warming_campaign: bool = False

class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    segment_rules: Optional[Dict[str, Any]] = None

# Dependency to get async database session with proper lifecycle management
async def get_async_db_session():
    """Get async database session with proper transaction management"""
    db = await get_async_db()
    try:
        yield db
        # Note: AsyncDatabaseManager handles its own connection lifecycle
        # No explicit commit needed as each operation auto-commits
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        # AsyncDatabaseManager handles rollback internally
        raise
    finally:
        # Connection is returned to pool automatically by AsyncDatabaseManager
        pass

# Legacy sync database session (for backward compatibility)
def get_db_session():
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0"
    }

# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with system overview"""
    return """
    <html>
        <head>
            <title>Email Delivery System</title>
        </head>
        <body>
            <h1>Email Delivery System API v2.0</h1>
            <p>Advanced email delivery system with multi-ESP support</p>
            <ul>
                <li><a href="/docs">API Documentation</a></li>
                <li><a href="/health">Health Check</a></li>
                <li><a href="/system/status">System Status</a></li>
                <li><a href="/dashboard">📊 Real-Time Dashboard</a></li>
            </ul>
        </body>
    </html>
    """

# Dashboard endpoint
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Real-time metrics dashboard"""
    try:
        with open("templates/dashboard.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return """
        <html>
            <body>
                <h1>Dashboard Not Found</h1>
                <p>The dashboard template is missing. Please ensure templates/dashboard.html exists.</p>
                <a href="/">← Back to Home</a>
            </body>
        </html>
        """

# System status endpoint
@app.get("/system/status")
async def system_status(db=Depends(get_async_db_session)):
    """Get comprehensive system status"""
    try:
        # Get ESP status
        provider_manager = ProviderManager(db)
        esp_status = provider_manager.get_provider_health_check()
        
        # Get rate limiting status
        rate_limit_status = rate_limit_manager.get_all_status()
        
        # Get database stats
        engagement_stats = await db.get_engagement_stats(days=7)
        
        return {
            "system_health": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "esp_providers": esp_status,
            "rate_limiting": rate_limit_status,
            "engagement_stats_7d": engagement_stats,
            "database_status": "connected"
        }
        
    except Exception as e:
        error_info = handle_error(e, {"endpoint": "system_status"})
        return {
            "system_health": "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "error": error_info['message']
        }

# Subscriber Management Endpoints
@app.post("/subscribers/", response_model=Dict)
async def create_subscriber(subscriber: SubscriberCreate, db=Depends(get_async_db_session)):
    """Add a new subscriber with async database operations"""
    try:
        # Validate email format
        if not subscriber.email or '@' not in subscriber.email:
            raise ValidationError("Invalid email format", "email", subscriber.email, "email_format")
        
        # Check if subscriber already exists
        existing = await db.get_subscriber_by_email(subscriber.email)
        if existing:
            raise HTTPException(status_code=400, detail="Subscriber already exists")
        
        # Insert new subscriber
        query = '''
            INSERT INTO subscribers (email, name, company, segment, source, custom_fields, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            subscriber.email,
            subscriber.name,
            subscriber.company,
            subscriber.segment,
            subscriber.source,
            json.dumps(subscriber.custom_fields) if subscriber.custom_fields else None,
            json.dumps(subscriber.tags) if subscriber.tags else None
        )
        
        await db.execute_update(query, params)
        
        logger.info(f"Created subscriber: {subscriber.email}")
        return {"success": True, "message": "Subscriber created successfully"}
        
    except ValidationError as e:
        error_info = handle_error(e, {"endpoint": "create_subscriber", "email": subscriber.email})
        raise HTTPException(status_code=400, detail=error_info['message'])
    except Exception as e:
        error_info = handle_error(e, {"endpoint": "create_subscriber", "email": subscriber.email})
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/subscribers/{email}")
async def get_subscriber(email: str, db=Depends(get_async_db_session)):
    """Get subscriber by email"""
    try:
        subscriber = await db.get_subscriber_by_email(email)
        
        if subscriber:
            return subscriber
        else:
            raise HTTPException(status_code=404, detail="Subscriber not found")
            
    except Exception as e:
        error_info = handle_error(e, {"endpoint": "get_subscriber", "email": email})
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/subscribers/")
async def list_subscribers(
    limit: int = 100, 
    offset: int = 0, 
    segment: Optional[str] = None,
    db=Depends(get_async_db_session)
):
    """List subscribers with pagination and filtering"""
    try:
        query = "SELECT * FROM subscribers WHERE status = 'active'"
        params = []
        
        if segment:
            query += " AND segment = ?"
            params.append(segment)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        subscribers = await db.execute_query(query, tuple(params))
        
        # Get total count
        count_query = "SELECT COUNT(*) as total FROM subscribers WHERE status = 'active'"
        count_params = []
        
        if segment:
            count_query += " AND segment = ?"
            count_params.append(segment)
        
        count_result = await db.execute_query(count_query, tuple(count_params))
        total = count_result[0]['total'] if count_result else 0
        
        return {
            "subscribers": subscribers,
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        error_info = handle_error(e, {"endpoint": "list_subscribers"})
        raise HTTPException(status_code=500, detail="Internal server error")

# Campaign Management Endpoints
@app.post("/campaigns/", response_model=Dict)
async def create_campaign(campaign: CampaignCreate, db=Depends(get_async_db_session)):
    """Create a new email campaign"""
    try:
        # Validate required fields
        if not campaign.name or not campaign.subject:
            raise ValidationError("Missing required fields", "name/subject", "", "required")
        
        # Insert campaign
        query = '''
            INSERT INTO campaigns 
            (name, subject, html_content, text_content, from_name, from_email, 
             segment_rules, warming_campaign, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft')
        '''
        params = (
            campaign.name,
            campaign.subject,
            campaign.html_content,
            campaign.text_content,
            campaign.from_name,
            campaign.from_email,
            json.dumps(campaign.segment_rules) if campaign.segment_rules else None,
            campaign.warming_campaign
        )
        
        await db.execute_update(query, params)
        
        logger.info(f"Created campaign: {campaign.name}")
        return {"success": True, "message": "Campaign created successfully"}
        
    except ValidationError as e:
        error_info = handle_error(e, {"endpoint": "create_campaign"})
        raise HTTPException(status_code=400, detail=error_info['message'])
    except Exception as e:
        error_info = handle_error(e, {"endpoint": "create_campaign"})
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    campaign_id: int, 
    warming_mode: bool = False, 
    background_tasks: BackgroundTasks = None,
    db=Depends(get_async_db_session)
):
    """Send email campaign with proper async/await"""
    try:
        # Initialize email engine with async database
        engine = EmailDeliveryEngine(db)
        
        if background_tasks:
            # Send campaign in background
            background_tasks.add_task(engine.send_campaign, campaign_id, warming_mode)
            return {
                "success": True,
                "message": "Campaign sending started in background",
                "campaign_id": campaign_id,
                "warming_mode": warming_mode
            }
        else:
            # Send synchronously with proper await
            results = await engine.send_campaign(campaign_id, warming_mode)
            
            logger.info(f"Campaign {campaign_id} send completed: {results.sent_count}/{results.total_recipients} sent")
            
            return {
                "success": True,
                "campaign_id": campaign_id,
                "total_recipients": results.total_recipients,
                "sent_count": results.sent_count,
                "failed_count": results.failed_count,
                "esp_distribution": results.esp_distribution,
                "start_time": results.start_time.isoformat(),
                "end_time": results.end_time.isoformat(),
                "warming_mode": warming_mode
            }
        
    except EmailDeliveryError as e:
        error_info = handle_error(e, {
            "endpoint": "send_campaign",
            "campaign_id": campaign_id,
            "warming_mode": warming_mode
        })
        logger.error(f"Campaign {campaign_id} send failed: {str(e)}")
        raise HTTPException(status_code=400, detail=error_info['message'])
    except Exception as e:
        error_info = handle_error(e, {
            "endpoint": "send_campaign",
            "campaign_id": campaign_id,
            "warming_mode": warming_mode
        })
        logger.error(f"Campaign {campaign_id} send failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Campaign send failed: {str(e)}")

# Analytics Endpoints
@app.get("/analytics/engagement")
async def get_engagement_analytics(
    campaign_id: Optional[int] = None,
    days: int = 30,
    db=Depends(get_async_db_session)
):
    """Get engagement analytics"""
    try:
        stats = await db.get_engagement_stats(campaign_id, days)
        return {
            "period_days": days,
            "campaign_id": campaign_id,
            "stats": stats,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_info = handle_error(e, {"endpoint": "get_engagement_analytics"})
        raise HTTPException(status_code=500, detail="Internal server error")

# Real-time Metrics Dashboard Endpoint
@app.get("/api/realtime-metrics")
async def get_realtime_metrics(
    hours: int = 24,
    db=Depends(get_async_db_session)
):
    """Get real-time performance metrics from actual delivery data"""
    try:
        # Real delivery rate from webhook events
        delivery_query = """
            SELECT
                COUNT(CASE WHEN event_type = 'delivered' THEN 1 END) as delivered,
                COUNT(CASE WHEN event_type IN ('sent', 'delivered', 'bounce') THEN 1 END) as total_sent,
                COUNT(CASE WHEN event_type = 'bounce' THEN 1 END) as bounced,
                COUNT(CASE WHEN event_type = 'open' THEN 1 END) as opened,
                COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicked,
                COUNT(CASE WHEN event_type = 'complaint' THEN 1 END) as complained
            FROM delivery_events
            WHERE timestamp > datetime('now', '-{} hours')
        """.format(hours)

        delivery_stats = await db.execute_query(delivery_query)

        if delivery_stats and delivery_stats[0]['total_sent'] > 0:
            stats = delivery_stats[0]
            delivery_rate = (stats['delivered'] / stats['total_sent']) * 100
            bounce_rate = (stats['bounced'] / stats['total_sent']) * 100
            open_rate = (stats['opened'] / stats['delivered']) * 100 if stats['delivered'] > 0 else 0
            click_rate = (stats['clicked'] / stats['delivered']) * 100 if stats['delivered'] > 0 else 0
            complaint_rate = (stats['complained'] / stats['total_sent']) * 100
        else:
            delivery_rate = bounce_rate = open_rate = click_rate = complaint_rate = 0
            stats = {'delivered': 0, 'total_sent': 0, 'bounced': 0, 'opened': 0, 'clicked': 0, 'complained': 0}

        # ESP breakdown
        esp_query = """
            SELECT
                esp_provider,
                COUNT(CASE WHEN event_type = 'delivered' THEN 1 END) as delivered,
                COUNT(CASE WHEN event_type IN ('sent', 'delivered', 'bounce') THEN 1 END) as sent,
                COUNT(CASE WHEN event_type = 'bounce' THEN 1 END) as bounced
            FROM delivery_events
            WHERE timestamp > datetime('now', '-{} hours')
            GROUP BY esp_provider
        """.format(hours)

        esp_stats = await db.execute_query(esp_query)
        esp_breakdown = {}

        for esp_stat in esp_stats:
            provider = esp_stat['esp_provider']
            sent = esp_stat['sent']
            delivered = esp_stat['delivered']
            bounced = esp_stat['bounced']

            esp_breakdown[provider] = {
                'sent': sent,
                'delivered': delivered,
                'bounced': bounced,
                'delivery_rate': (delivered / sent * 100) if sent > 0 else 0,
                'bounce_rate': (bounced / sent * 100) if sent > 0 else 0
            }

        return {
            "real_metrics": {
                "period_hours": hours,
                "delivery_rate": round(delivery_rate, 2),
                "bounce_rate": round(bounce_rate, 2),
                "open_rate": round(open_rate, 2),
                "click_rate": round(click_rate, 2),
                "complaint_rate": round(complaint_rate, 2),
                "total_sent": stats['total_sent'],
                "total_delivered": stats['delivered'],
                "total_bounced": stats['bounced'],
                "total_opened": stats['opened'],
                "total_clicked": stats['clicked'],
                "total_complained": stats['complained'],
                "esp_breakdown": esp_breakdown,
                "last_updated": datetime.utcnow().isoformat(),
                "data_source": "real_webhook_events"
            }
        }

    except Exception as e:
        error_info = handle_error(e, {"endpoint": "realtime_metrics"})
        raise HTTPException(status_code=500, detail="Internal server error")

# ESP Management Endpoints
@app.get("/esp/status")
async def get_esp_status(db=Depends(get_async_db_session)):
    """Get ESP provider status"""
    try:
        provider_manager = ProviderManager(db)
        status = provider_manager.get_provider_health_check()
        
        return {
            "providers": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_info = handle_error(e, {"endpoint": "get_esp_status"})
        raise HTTPException(status_code=500, detail="Internal server error")

# Rate Limiting Endpoints
@app.get("/rate-limits/status")
async def get_rate_limit_status():
    """Get rate limiting status for all ESPs"""
    try:
        status = rate_limit_manager.get_all_status()
        return {
            "rate_limits": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_info = handle_error(e, {"endpoint": "get_rate_limit_status"})
        raise HTTPException(status_code=500, detail="Internal server error")

# IP Warming Endpoints
@app.get("/warming/{provider}/status")
async def get_warming_status(provider: str, db=Depends(get_async_db_session)):
    """Get IP warming status for provider"""
    try:
        warming_system = IPWarmingSchedule()
        status = warming_system.get_warming_status(db, provider)
        
        return status
        
    except Exception as e:
        error_info = handle_error(e, {"endpoint": "get_warming_status", "provider": provider})
        raise HTTPException(status_code=500, detail="Internal server error")

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and system components on startup"""
    try:
        # Initialize async database
        async_db = await get_async_db()
        logger.info("Async database initialized successfully")
        
        # Initialize rate limiting
        logger.info("Rate limiting system initialized")
        
        logger.info("Email Delivery System API v2.0 started successfully")
        
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    try:
        # Close database connections
        async_db = await get_async_db()
        await async_db.close_all_connections()
        
        logger.info("Email Delivery System API shutdown completed")
        
    except Exception as e:
        logger.error(f"Shutdown error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
