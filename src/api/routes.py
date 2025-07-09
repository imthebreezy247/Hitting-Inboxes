# src/api/routes.py
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from typing import List, Dict, Optional
from datetime import datetime
import asyncio

from ..database.models import get_db, create_tables
from ..database.subscriber_manager import SubscriberManager
from ..database.engagement_tracker import EngagementTracker
from ..core.email_engine import EmailDeliveryEngine
from ..core.warming_system import IPWarmingSchedule
from ..core.provider_manager import ProviderManager

# Initialize FastAPI app
app = FastAPI(
    title="Email Delivery System API",
    description="High-deliverability email system with multi-ESP support",
    version="2.0.0"
)

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()

# Pydantic models for request/response
class SubscriberCreate(BaseModel):
    email: EmailStr
    name: str
    company: Optional[str] = None
    segment: str = 'general'
    source: Optional[str] = None
    custom_fields: Optional[Dict] = None
    tags: Optional[List[str]] = None

class SubscriberUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    segment: Optional[str] = None
    custom_fields: Optional[Dict] = None
    tags: Optional[List[str]] = None
    time_zone: Optional[str] = None

class CampaignCreate(BaseModel):
    name: str
    subject: str
    html_content: str
    text_content: Optional[str] = None
    from_name: Optional[str] = "Chris - CJS Insurance Solutions"
    from_email: Optional[str] = "chris@mail.cjsinsurancesolutions.com"
    segment_rules: Optional[Dict] = None
    scheduled_time: Optional[datetime] = None
    send_time_optimization: bool = True
    warming_campaign: bool = False

class EngagementEvent(BaseModel):
    message_id: Optional[str] = None
    engagement_id: Optional[int] = None
    event_type: str  # open, click, bounce, complaint, unsubscribe
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    clicked_url: Optional[str] = None
    bounce_type: Optional[str] = None
    bounce_reason: Optional[str] = None

# Dependency to get database session
def get_db_session():
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()

# Subscriber Management Endpoints
@app.post("/subscribers/", response_model=Dict)
async def create_subscriber(subscriber: SubscriberCreate, db=Depends(get_db_session)):
    """Add a new subscriber"""
    manager = SubscriberManager(db)
    success, message = manager.add_subscriber(
        email=subscriber.email,
        name=subscriber.name,
        company=subscriber.company,
        segment=subscriber.segment,
        source=subscriber.source,
        custom_fields=subscriber.custom_fields,
        tags=subscriber.tags
    )
    
    if success:
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)

@app.get("/subscribers/{email}")
async def get_subscriber(email: str, db=Depends(get_db_session)):
    """Get subscriber by email"""
    manager = SubscriberManager(db)
    subscriber = manager.get_subscriber(email)
    
    if subscriber:
        return subscriber
    else:
        raise HTTPException(status_code=404, detail="Subscriber not found")

@app.put("/subscribers/{email}")
async def update_subscriber(email: str, updates: SubscriberUpdate, db=Depends(get_db_session)):
    """Update subscriber information"""
    manager = SubscriberManager(db)
    success, message = manager.update_subscriber(
        email=email,
        **updates.dict(exclude_unset=True)
    )
    
    if success:
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)

@app.delete("/subscribers/{email}")
async def unsubscribe_subscriber(email: str, reason: Optional[str] = None, db=Depends(get_db_session)):
    """Unsubscribe a subscriber"""
    manager = SubscriberManager(db)
    success, message = manager.unsubscribe(email, reason)
    
    if success:
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)

@app.get("/subscribers/segment/{segment}")
async def get_subscribers_by_segment(segment: str, limit: Optional[int] = None, 
                                   min_engagement: Optional[float] = None,
                                   db=Depends(get_db_session)):
    """Get subscribers by segment"""
    manager = SubscriberManager(db)
    subscribers = manager.get_subscribers_by_segment(segment, limit, min_engagement)
    return {"subscribers": subscribers, "count": len(subscribers)}

@app.post("/subscribers/bulk-import")
async def bulk_import_subscribers(subscribers: List[SubscriberCreate], db=Depends(get_db_session)):
    """Bulk import subscribers"""
    manager = SubscriberManager(db)
    
    # Convert Pydantic models to dicts
    subscribers_data = [sub.dict() for sub in subscribers]
    
    result = manager.bulk_import(subscribers_data)
    return result

@app.get("/subscribers/stats")
async def get_subscriber_stats(db=Depends(get_db_session)):
    """Get subscriber statistics"""
    manager = SubscriberManager(db)
    stats = manager.get_engagement_statistics()
    return stats

# Campaign Management Endpoints
@app.post("/campaigns/")
async def create_campaign(campaign: CampaignCreate, db=Depends(get_db_session)):
    """Create a new email campaign"""
    from ..database.models import Campaign
    
    new_campaign = Campaign(
        name=campaign.name,
        subject=campaign.subject,
        html_content=campaign.html_content,
        text_content=campaign.text_content,
        from_name=campaign.from_name,
        from_email=campaign.from_email,
        segment_rules=campaign.segment_rules,
        scheduled_time=campaign.scheduled_time,
        send_time_optimization=campaign.send_time_optimization,
        warming_campaign=campaign.warming_campaign,
        status='draft'
    )
    
    try:
        db.add(new_campaign)
        db.commit()
        db.refresh(new_campaign)
        
        return {
            "success": True,
            "campaign_id": new_campaign.id,
            "message": "Campaign created successfully"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create campaign: {str(e)}")

@app.post("/campaigns/{campaign_id}/send")
async def send_campaign(campaign_id: int, warming_mode: bool = False, 
                       background_tasks: BackgroundTasks = None,
                       db=Depends(get_db_session)):
    """Send a campaign"""
    
    # Initialize email engine
    engine = EmailDeliveryEngine(db)
    
    try:
        # Send campaign in background
        if background_tasks:
            background_tasks.add_task(engine.send_campaign, campaign_id, warming_mode)
            return {
                "success": True,
                "message": "Campaign sending started in background",
                "campaign_id": campaign_id
            }
        else:
            # Send synchronously (for testing)
            results = await engine.send_campaign(campaign_id, warming_mode)
            return {
                "success": True,
                "results": results,
                "campaign_id": campaign_id
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send campaign: {str(e)}")

@app.get("/campaigns/{campaign_id}/stats")
async def get_campaign_stats(campaign_id: int, db=Depends(get_db_session)):
    """Get campaign engagement statistics"""
    tracker = EngagementTracker(db)
    stats = tracker.get_campaign_engagement_stats(campaign_id)
    
    if stats:
        return stats
    else:
        raise HTTPException(status_code=404, detail="Campaign not found or no stats available")

# Engagement Tracking Endpoints
@app.post("/engagement/track")
async def track_engagement(event: EngagementEvent, db=Depends(get_db_session)):
    """Track engagement events (opens, clicks, bounces, etc.)"""
    tracker = EngagementTracker(db)
    
    success = False
    
    if event.event_type == 'open':
        success = tracker.track_open(
            engagement_id=event.engagement_id,
            message_id=event.message_id,
            user_agent=event.user_agent,
            ip_address=event.ip_address
        )
    elif event.event_type == 'click':
        success = tracker.track_click(
            engagement_id=event.engagement_id,
            message_id=event.message_id,
            clicked_url=event.clicked_url,
            user_agent=event.user_agent,
            ip_address=event.ip_address
        )
    elif event.event_type == 'bounce':
        success = tracker.track_bounce(
            engagement_id=event.engagement_id,
            message_id=event.message_id,
            bounce_type=event.bounce_type or 'hard',
            bounce_reason=event.bounce_reason
        )
    elif event.event_type == 'complaint':
        success = tracker.track_complaint(
            engagement_id=event.engagement_id,
            message_id=event.message_id
        )
    elif event.event_type == 'unsubscribe':
        success = tracker.track_unsubscribe(
            engagement_id=event.engagement_id,
            message_id=event.message_id
        )
    elif event.event_type == 'delivery':
        success = tracker.track_delivery(
            engagement_id=event.engagement_id,
            message_id=event.message_id
        )
    
    if success:
        return {"success": True, "message": f"{event.event_type} tracked successfully"}
    else:
        raise HTTPException(status_code=400, detail=f"Failed to track {event.event_type}")

# System Status and Monitoring
@app.get("/system/status")
async def get_system_status(db=Depends(get_db_session)):
    """Get overall system status"""
    try:
        # Provider status
        provider_manager = ProviderManager(db_session=db)
        provider_stats = provider_manager.get_provider_stats()
        
        # Warming status
        warming_schedule = IPWarmingSchedule()
        warming_status = warming_schedule.get_warming_status(db, 'sendgrid')
        
        # Subscriber stats
        subscriber_manager = SubscriberManager(db)
        subscriber_stats = subscriber_manager.get_engagement_statistics()
        
        return {
            "system_status": "operational",
            "timestamp": datetime.utcnow().isoformat(),
            "providers": provider_stats,
            "warming": warming_status,
            "subscribers": subscriber_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")

@app.get("/system/providers")
async def get_provider_status(db=Depends(get_db_session)):
    """Get detailed provider status"""
    provider_manager = ProviderManager(db_session=db)
    return provider_manager.get_provider_stats()

@app.get("/system/warming")
async def get_warming_status(provider: str = 'sendgrid', db=Depends(get_db_session)):
    """Get IP warming status"""
    warming_schedule = IPWarmingSchedule()
    status = warming_schedule.get_warming_status(db, provider)
    return status

# Engagement Analytics
@app.get("/analytics/trends")
async def get_engagement_trends(days: int = 30, db=Depends(get_db_session)):
    """Get engagement trends over specified period"""
    tracker = EngagementTracker(db)
    trends = tracker.get_engagement_trends(days)
    return trends

@app.get("/analytics/subscriber/{subscriber_id}/history")
async def get_subscriber_history(subscriber_id: int, limit: int = 50, db=Depends(get_db_session)):
    """Get engagement history for a subscriber"""
    tracker = EngagementTracker(db)
    history = tracker.get_subscriber_engagement_history(subscriber_id, limit)
    return {"subscriber_id": subscriber_id, "history": history}

# Utility Endpoints
@app.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_page(email: str, db=Depends(get_db_session)):
    """Unsubscribe page for email links"""
    manager = SubscriberManager(db)
    success, message = manager.unsubscribe(email, "web_unsubscribe")
    
    if success:
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h2>Successfully Unsubscribed</h2>
                <p>You have been successfully unsubscribed from our mailing list.</p>
                <p>Email: {email}</p>
            </body>
        </html>
        """
    else:
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h2>Unsubscribe Error</h2>
                <p>There was an error processing your unsubscribe request.</p>
                <p>Error: {message}</p>
            </body>
        </html>
        """

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Email Delivery System API v2.0",
        "status": "operational",
        "features": [
            "Multi-ESP support (SendGrid, Amazon SES, Postmark)",
            "IP warming automation",
            "Advanced engagement tracking",
            "Subscriber management",
            "Campaign analytics",
            "Real-time monitoring"
        ]
    }
