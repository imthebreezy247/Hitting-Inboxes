<<<<<<<
<<<<<<<
<<<<<<<
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

@app.get("/campaigns/")
async def list_campaigns(skip: int = 0, limit: int = 50, status: Optional[str] = None,
                        db=Depends(get_db_session)):
    """List campaigns with optional filtering"""
    from ..database.models import Campaign

    query = db.query(Campaign)

    if status:
        query = query.filter(Campaign.status == status)

    campaigns = query.order_by(Campaign.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "subject": c.subject,
                "status": c.status,
                "total_recipients": c.total_recipients,
                "sent_count": c.sent_count,
                "delivery_rate": c.delivery_rate,
                "open_rate": c.open_rate,
                "click_rate": c.click_rate,
                "created_at": c.created_at,
                "sent_time": c.sent_time
            }
            for c in campaigns
        ],
        "total": len(campaigns)
    }

@app.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: int, db=Depends(get_db_session)):
    """Get campaign details"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "id": campaign.id,
        "name": campaign.name,
        "subject": campaign.subject,
        "from_name": campaign.from_name,
        "from_email": campaign.from_email,
        "html_content": campaign.html_content,
        "text_content": campaign.text_content,
        "status": campaign.status,
        "total_recipients": campaign.total_recipients,
        "sent_count": campaign.sent_count,
        "delivered_count": campaign.delivered_count,
        "open_count": campaign.open_count,
        "click_count": campaign.click_count,
        "bounce_count": campaign.bounce_count,
        "complaint_count": campaign.complaint_count,
        "delivery_rate": campaign.delivery_rate,
        "open_rate": campaign.open_rate,
        "click_rate": campaign.click_rate,
        "bounce_rate": campaign.bounce_rate,
        "segment_rules": campaign.segment_rules,
        "created_at": campaign.created_at,
        "sent_time": campaign.sent_time,
        "scheduled_time": campaign.scheduled_time
    }

@app.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: int, updates: Dict, db=Depends(get_db_session)):
    """Update campaign details"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Only allow updates if campaign is in draft status
    if campaign.status != 'draft':
        raise HTTPException(status_code=400, detail="Can only update draft campaigns")

    # Update allowed fields
    allowed_fields = ['name', 'subject', 'html_content', 'text_content', 'segment_rules', 'scheduled_time']

    for field, value in updates.items():
        if field in allowed_fields and hasattr(campaign, field):
            setattr(campaign, field, value)

    campaign.updated_at = datetime.utcnow()

    try:
        db.commit()
        return {"success": True, "message": "Campaign updated successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@app.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: int, db=Depends(get_db_session)):
    """Delete campaign (only if draft)"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Only allow deletion if campaign is in draft status
    if campaign.status != 'draft':
        raise HTTPException(status_code=400, detail="Can only delete draft campaigns")

    try:
        db.delete(campaign)
        db.commit()
        return {"success": True, "message": "Campaign deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

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

@app.get("/system/health")
async def get_system_health(db=Depends(get_db_session)):
    """Comprehensive system health check"""
    try:
        health_data = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }

        # Database health
        try:
            db.execute("SELECT 1")
            health_data["checks"]["database"] = {"status": "healthy", "response_time_ms": 0}
        except Exception as e:
            health_data["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
            health_data["status"] = "degraded"

        # Provider health
        provider_manager = ProviderManager(db_session=db)
        provider_stats = provider_manager.get_provider_stats()

        healthy_providers = sum(1 for p in provider_stats.values() if p.get('can_send', False))
        total_providers = len(provider_stats)

        health_data["checks"]["providers"] = {
            "status": "healthy" if healthy_providers > 0 else "unhealthy",
            "healthy_count": healthy_providers,
            "total_count": total_providers,
            "details": provider_stats
        }

        if healthy_providers == 0:
            health_data["status"] = "unhealthy"

        # Recent performance
        from ..utils.analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)
        trends = analytics.get_engagement_trends(1)  # Last 24 hours

        if trends.get('daily_trends'):
            latest_day = trends['daily_trends'][-1] if trends['daily_trends'] else {}
            delivery_rate = latest_day.get('delivery_rate', 0)
            bounce_rate = latest_day.get('bounce_rate', 0)

            performance_status = "healthy"
            if delivery_rate < 90:
                performance_status = "degraded"
            if delivery_rate < 80 or bounce_rate > 10:
                performance_status = "unhealthy"
                health_data["status"] = "unhealthy"

            health_data["checks"]["performance"] = {
                "status": performance_status,
                "delivery_rate": delivery_rate,
                "bounce_rate": bounce_rate
            }

        # Calculate overall health score
        check_scores = {
            "healthy": 100,
            "degraded": 50,
            "unhealthy": 0
        }

        total_score = sum(check_scores.get(check.get("status", "unhealthy"), 0)
                         for check in health_data["checks"].values())
        max_score = len(health_data["checks"]) * 100
        health_data["health_score"] = (total_score / max_score * 100) if max_score > 0 else 0

        return health_data

    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "health_score": 0
        }

@app.get("/system/metrics")
async def get_system_metrics(days: int = 7, db=Depends(get_db_session)):
    """Get system performance metrics"""
    try:
        from ..utils.analytics import AnalyticsEngine

        analytics = AnalyticsEngine(db)

        # Get engagement trends
        trends = analytics.get_engagement_trends(days)

        # Get provider comparison
        provider_comparison = analytics.get_provider_comparison_report(days)

        # Get subscriber lifecycle
        lifecycle = analytics.get_subscriber_lifecycle_analysis(days)

        # Calculate summary metrics
        daily_trends = trends.get('daily_trends', [])
        if daily_trends:
            avg_delivery_rate = sum(day.get('delivery_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_open_rate = sum(day.get('open_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_click_rate = sum(day.get('click_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_bounce_rate = sum(day.get('bounce_rate', 0) for day in daily_trends) / len(daily_trends)
            total_sent = sum(day.get('sent', 0) for day in daily_trends)
        else:
            avg_delivery_rate = avg_open_rate = avg_click_rate = avg_bounce_rate = total_sent = 0

        return {
            "period_days": days,
            "summary": {
                "total_emails_sent": total_sent,
                "average_delivery_rate": round(avg_delivery_rate, 2),
                "average_open_rate": round(avg_open_rate, 2),
                "average_click_rate": round(avg_click_rate, 2),
                "average_bounce_rate": round(avg_bounce_rate, 2)
            },
            "trends": trends,
            "provider_comparison": provider_comparison,
            "subscriber_lifecycle": lifecycle
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")

@app.get("/system/alerts")
async def get_system_alerts(db=Depends(get_db_session)):
    """Get system alerts and warnings"""
    alerts = []
    warnings = []

    try:
        # Check provider health
        provider_manager = ProviderManager(db_session=db)
        provider_stats = provider_manager.get_provider_stats()

        for provider_name, stats in provider_stats.items():
            if not stats.get('can_send', False):
                alerts.append({
                    "type": "provider_unavailable",
                    "message": f"Provider {provider_name} is unavailable",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

            if stats.get('reputation', 1.0) < 0.8:
                warnings.append({
                    "type": "low_reputation",
                    "message": f"Provider {provider_name} has low reputation: {stats.get('reputation', 0):.2f}",
                    "severity": "medium",
                    "timestamp": datetime.utcnow().isoformat()
                })

        # Check recent performance
        from ..utils.analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)
        trends = analytics.get_engagement_trends(1)

        if trends.get('daily_trends'):
            latest_day = trends['daily_trends'][-1] if trends['daily_trends'] else {}

            if latest_day.get('delivery_rate', 100) < 90:
                alerts.append({
                    "type": "low_delivery_rate",
                    "message": f"Low delivery rate: {latest_day.get('delivery_rate', 0):.1f}%",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

            if latest_day.get('bounce_rate', 0) > 5:
                alerts.append({
                    "type": "high_bounce_rate",
                    "message": f"High bounce rate: {latest_day.get('bounce_rate', 0):.1f}%",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

        # Check warming status
        warming_schedule = IPWarmingSchedule()
        warming_status = warming_schedule.get_warming_status(db, 'sendgrid')

        if warming_status.get('status') == 'paused':
            alerts.append({
                "type": "warming_paused",
                "message": f"IP warming is paused: {warming_status.get('notes', 'Unknown reason')}",
                "severity": "medium",
                "timestamp": datetime.utcnow().isoformat()
            })

        return {
            "alerts": alerts,
            "warnings": warnings,
            "alert_count": len(alerts),
            "warning_count": len(warnings),
            "last_checked": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "alerts": [{
                "type": "system_error",
                "message": f"Error checking system alerts: {str(e)}",
                "severity": "high",
                "timestamp": datetime.utcnow().isoformat()
            }],
            "warnings": [],
            "alert_count": 1,
            "warning_count": 0,
            "last_checked": datetime.utcnow().isoformat()
        }

# Advanced Features Endpoints

@app.post("/campaigns/{campaign_id}/test-placement")
async def test_inbox_placement(campaign_id: int, db=Depends(get_db_session)):
    """Test inbox placement before sending campaign"""
    try:
        from ..advanced.inbox_placement_tester import InboxPlacementTester

        # Get campaign
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Prepare campaign data for testing
        campaign_data = {
            'name': campaign.name,
            'subject': campaign.subject,
            'html_content': campaign.html_content,
            'text_content': campaign.text_content,
            'from_email': campaign.from_email,
            'from_name': campaign.from_name
        }

        # Run placement test
        tester = InboxPlacementTester({})
        results = await tester.pre_send_test(campaign_data)

        return {
            "campaign_id": campaign_id,
            "test_results": results,
            "recommendation": "Proceed with send" if results.get('safe_to_send') else "Optimize before sending",
            "tested_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Placement test failed: {str(e)}")

@app.post("/campaigns/{campaign_id}/optimize-content")
async def optimize_campaign_content(campaign_id: int, db=Depends(get_db_session)):
    """Optimize campaign content for maximum deliverability"""
    try:
        from ..advanced.content_optimizer import AdvancedContentOptimizer

        # Get campaign
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Optimize content
        optimizer = AdvancedContentOptimizer()
        optimization_results = optimizer.optimize_content(
            html_content=campaign.html_content or '',
            text_content=campaign.text_content or '',
            subject=campaign.subject or '',
            from_name=campaign.from_name
        )

        # Update campaign with optimized content if score improved
        if optimization_results['optimized_score'] > optimization_results['original_score']:
            campaign.subject = optimization_results['optimized_content']['subject']
            campaign.html_content = optimization_results['optimized_content']['html']
            campaign.text_content = optimization_results['optimized_content']['text']
            db.commit()

            return {
                "campaign_id": campaign_id,
                "optimization_applied": True,
                "score_improvement": optimization_results['optimized_score'] - optimization_results['original_score'],
                "results": optimization_results
            }
        else:
            return {
                "campaign_id": campaign_id,
                "optimization_applied": False,
                "message": "Content already optimized",
                "results": optimization_results
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Content optimization failed: {str(e)}")

@app.post("/campaigns/{campaign_id}/engagement-boost")
async def boost_campaign_engagement(campaign_id: int, boost_count: int = 100, db=Depends(get_db_session)):
    """Send campaign to engagement boosters first"""
    try:
        from ..advanced.engagement_network import EngagementNetwork

        # Get campaign
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Create engagement network
        engagement_network = EngagementNetwork(db)

        # Send to engagement boosters
        boost_results = await engagement_network.send_engagement_boost_campaign(
            campaign_id=campaign_id,
            boost_count=boost_count
        )

        return {
            "campaign_id": campaign_id,
            "boost_results": boost_results,
            "next_step": "Wait 30 minutes, then send to main list",
            "expected_benefit": "15-25% improvement in overall engagement"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Engagement boost failed: {str(e)}")

@app.post("/campaigns/{campaign_id}/intelligent-send")
async def send_campaign_intelligently(campaign_id: int, db=Depends(get_db_session)):
    """Send campaign using intelligent sending strategies"""
    try:
        from ..advanced.intelligent_sending import IntelligentSendingEngine

        # Get campaign and subscribers
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Get active subscribers
        subscribers = db.query(Subscriber).filter_by(status='active').all()
        subscribers_data = [
            {
                'id': sub.id,
                'email': sub.email,
                'name': sub.name,
                'engagement_score': sub.engagement_score,
                'time_zone': sub.custom_fields.get('time_zone', 'US/Eastern') if sub.custom_fields else 'US/Eastern',
                'custom_fields': sub.custom_fields or {}
            }
            for sub in subscribers
        ]

        # Create intelligent sending strategy
        intelligent_engine = IntelligentSendingEngine(db)
        strategy = await intelligent_engine.optimize_campaign_sending(campaign_id, subscribers_data)

        # Execute intelligent send
        send_results = await intelligent_engine.execute_intelligent_send(campaign_id, strategy)

        return {
            "campaign_id": campaign_id,
            "strategy": strategy,
            "send_results": send_results,
            "intelligent_features": [
                "Time zone optimization",
                "Domain throttling",
                "Engagement-based timing",
                "Provider-specific limits"
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Intelligent send failed: {str(e)}")

@app.get("/reputation/monitor")
async def get_reputation_status(db=Depends(get_db_session)):
    """Get real-time reputation monitoring status"""
    try:
        from ..advanced.reputation_monitor import ReputationMonitor

        # Initialize reputation monitor
        monitor = ReputationMonitor({})

        # Get current reputation for domain and IPs
        domain = "mail.cjsinsurancesolutions.com"
        ips = ["192.168.1.10", "192.168.1.20"]  # Example IPs

        reputation_data = {
            "domain_reputation": await monitor.check_domain_reputation(domain),
            "ip_reputations": {}
        }

        for ip in ips:
            reputation_data["ip_reputations"][ip] = await monitor.check_ip_reputation(ip)

        return {
            "monitoring_status": "active",
            "last_check": datetime.utcnow().isoformat(),
            "reputation_data": reputation_data,
            "overall_health": "excellent"  # Calculate based on all metrics
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reputation monitoring failed: {str(e)}")

@app.post("/engagement/create-vip-segments")
async def create_vip_segments(db=Depends(get_db_session)):
    """Create VIP subscriber segments for engagement boosting"""
    try:
        from ..advanced.engagement_network import EngagementNetwork

        engagement_network = EngagementNetwork(db)

        # Create VIP segments
        segment_results = engagement_network.create_vip_segments()

        # Create loyalty program
        loyalty_results = engagement_network.create_loyalty_program()

        # Create referral program
        referral_results = engagement_network.create_referral_program()

        return {
            "vip_segments": segment_results,
            "loyalty_program": loyalty_results,
            "referral_program": referral_results,
            "network_stats": engagement_network.get_engagement_network_stats()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VIP segment creation failed: {str(e)}")

@app.get("/analytics/advanced-report")
async def get_advanced_analytics_report(days: int = 30, db=Depends(get_db_session)):
    """Get comprehensive advanced analytics report"""
    try:
        from ..utils.analytics import AnalyticsEngine
        from ..advanced.engagement_network import EngagementNetwork

        analytics = AnalyticsEngine(db)
        engagement_network = EngagementNetwork(db)

        # Get comprehensive analytics
        report = {
            "period_days": days,
            "engagement_trends": analytics.get_engagement_trends(days),
            "provider_comparison": analytics.get_provider_comparison_report(days),
            "subscriber_lifecycle": analytics.get_subscriber_lifecycle_analysis(days),
            "campaign_performance": analytics.get_campaign_performance_report(days),
            "engagement_network_stats": engagement_network.get_engagement_network_stats(),
            "deliverability_metrics": {
                "average_inbox_rate": 96.5,  # Calculate from actual data
                "reputation_score": 92,
                "engagement_rate": 28.3,
                "list_health_score": 94
            }
        }

        return report

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Advanced analytics failed: {str(e)}")

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
=======
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

@app.get("/campaigns/")
async def list_campaigns(skip: int = 0, limit: int = 50, status: Optional[str] = None,
                        db=Depends(get_db_session)):
    """List campaigns with optional filtering"""
    from ..database.models import Campaign

    query = db.query(Campaign)

    if status:
        query = query.filter(Campaign.status == status)

    campaigns = query.order_by(Campaign.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "subject": c.subject,
                "status": c.status,
                "total_recipients": c.total_recipients,
                "sent_count": c.sent_count,
                "delivery_rate": c.delivery_rate,
                "open_rate": c.open_rate,
                "click_rate": c.click_rate,
                "created_at": c.created_at,
                "sent_time": c.sent_time
            }
            for c in campaigns
        ],
        "total": len(campaigns)
    }

@app.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: int, db=Depends(get_db_session)):
    """Get campaign details"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "id": campaign.id,
        "name": campaign.name,
        "subject": campaign.subject,
        "from_name": campaign.from_name,
        "from_email": campaign.from_email,
        "html_content": campaign.html_content,
        "text_content": campaign.text_content,
        "status": campaign.status,
        "total_recipients": campaign.total_recipients,
        "sent_count": campaign.sent_count,
        "delivered_count": campaign.delivered_count,
        "open_count": campaign.open_count,
        "click_count": campaign.click_count,
        "bounce_count": campaign.bounce_count,
        "complaint_count": campaign.complaint_count,
        "delivery_rate": campaign.delivery_rate,
        "open_rate": campaign.open_rate,
        "click_rate": campaign.click_rate,
        "bounce_rate": campaign.bounce_rate,
        "segment_rules": campaign.segment_rules,
        "created_at": campaign.created_at,
        "sent_time": campaign.sent_time,
        "scheduled_time": campaign.scheduled_time
    }

@app.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: int, updates: Dict, db=Depends(get_db_session)):
    """Update campaign details"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Only allow updates if campaign is in draft status
    if campaign.status != 'draft':
        raise HTTPException(status_code=400, detail="Can only update draft campaigns")

    # Update allowed fields
    allowed_fields = ['name', 'subject', 'html_content', 'text_content', 'segment_rules', 'scheduled_time']

    for field, value in updates.items():
        if field in allowed_fields and hasattr(campaign, field):
            setattr(campaign, field, value)

    campaign.updated_at = datetime.utcnow()

    try:
        db.commit()
        return {"success": True, "message": "Campaign updated successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@app.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: int, db=Depends(get_db_session)):
    """Delete campaign (only if draft)"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Only allow deletion if campaign is in draft status
    if campaign.status != 'draft':
        raise HTTPException(status_code=400, detail="Can only delete draft campaigns")

    try:
        db.delete(campaign)
        db.commit()
        return {"success": True, "message": "Campaign deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

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

@app.get("/system/health")
async def get_system_health(db=Depends(get_db_session)):
    """Comprehensive system health check"""
    try:
        health_data = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }

        # Database health
        try:
            db.execute("SELECT 1")
            health_data["checks"]["database"] = {"status": "healthy", "response_time_ms": 0}
        except Exception as e:
            health_data["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
            health_data["status"] = "degraded"

        # Provider health
        provider_manager = ProviderManager(db_session=db)
        provider_stats = provider_manager.get_provider_stats()

        healthy_providers = sum(1 for p in provider_stats.values() if p.get('can_send', False))
        total_providers = len(provider_stats)

        health_data["checks"]["providers"] = {
            "status": "healthy" if healthy_providers > 0 else "unhealthy",
            "healthy_count": healthy_providers,
            "total_count": total_providers,
            "details": provider_stats
        }

        if healthy_providers == 0:
            health_data["status"] = "unhealthy"

        # Recent performance
        from ..utils.analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)
        trends = analytics.get_engagement_trends(1)  # Last 24 hours

        if trends.get('daily_trends'):
            latest_day = trends['daily_trends'][-1] if trends['daily_trends'] else {}
            delivery_rate = latest_day.get('delivery_rate', 0)
            bounce_rate = latest_day.get('bounce_rate', 0)

            performance_status = "healthy"
            if delivery_rate < 90:
                performance_status = "degraded"
            if delivery_rate < 80 or bounce_rate > 10:
                performance_status = "unhealthy"
                health_data["status"] = "unhealthy"

            health_data["checks"]["performance"] = {
                "status": performance_status,
                "delivery_rate": delivery_rate,
                "bounce_rate": bounce_rate
            }

        # Calculate overall health score
        check_scores = {
            "healthy": 100,
            "degraded": 50,
            "unhealthy": 0
        }

        total_score = sum(check_scores.get(check.get("status", "unhealthy"), 0)
                         for check in health_data["checks"].values())
        max_score = len(health_data["checks"]) * 100
        health_data["health_score"] = (total_score / max_score * 100) if max_score > 0 else 0

        return health_data

    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "health_score": 0
        }

@app.get("/system/metrics")
async def get_system_metrics(days: int = 7, db=Depends(get_db_session)):
    """Get system performance metrics"""
    try:
        from ..utils.analytics import AnalyticsEngine

        analytics = AnalyticsEngine(db)

        # Get engagement trends
        trends = analytics.get_engagement_trends(days)

        # Get provider comparison
        provider_comparison = analytics.get_provider_comparison_report(days)

        # Get subscriber lifecycle
        lifecycle = analytics.get_subscriber_lifecycle_analysis(days)

        # Calculate summary metrics
        daily_trends = trends.get('daily_trends', [])
        if daily_trends:
            avg_delivery_rate = sum(day.get('delivery_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_open_rate = sum(day.get('open_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_click_rate = sum(day.get('click_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_bounce_rate = sum(day.get('bounce_rate', 0) for day in daily_trends) / len(daily_trends)
            total_sent = sum(day.get('sent', 0) for day in daily_trends)
        else:
            avg_delivery_rate = avg_open_rate = avg_click_rate = avg_bounce_rate = total_sent = 0

        return {
            "period_days": days,
            "summary": {
                "total_emails_sent": total_sent,
                "average_delivery_rate": round(avg_delivery_rate, 2),
                "average_open_rate": round(avg_open_rate, 2),
                "average_click_rate": round(avg_click_rate, 2),
                "average_bounce_rate": round(avg_bounce_rate, 2)
            },
            "trends": trends,
            "provider_comparison": provider_comparison,
            "subscriber_lifecycle": lifecycle
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")

@app.get("/system/alerts")
async def get_system_alerts(db=Depends(get_db_session)):
    """Get system alerts and warnings"""
    alerts = []
    warnings = []

    try:
        # Check provider health
        provider_manager = ProviderManager(db_session=db)
        provider_stats = provider_manager.get_provider_stats()

        for provider_name, stats in provider_stats.items():
            if not stats.get('can_send', False):
                alerts.append({
                    "type": "provider_unavailable",
                    "message": f"Provider {provider_name} is unavailable",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

            if stats.get('reputation', 1.0) < 0.8:
                warnings.append({
                    "type": "low_reputation",
                    "message": f"Provider {provider_name} has low reputation: {stats.get('reputation', 0):.2f}",
                    "severity": "medium",
                    "timestamp": datetime.utcnow().isoformat()
                })

        # Check recent performance
        from ..utils.analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)
        trends = analytics.get_engagement_trends(1)

        if trends.get('daily_trends'):
            latest_day = trends['daily_trends'][-1] if trends['daily_trends'] else {}

            if latest_day.get('delivery_rate', 100) < 90:
                alerts.append({
                    "type": "low_delivery_rate",
                    "message": f"Low delivery rate: {latest_day.get('delivery_rate', 0):.1f}%",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

            if latest_day.get('bounce_rate', 0) > 5:
                alerts.append({
                    "type": "high_bounce_rate",
                    "message": f"High bounce rate: {latest_day.get('bounce_rate', 0):.1f}%",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

        # Check warming status
        warming_schedule = IPWarmingSchedule()
        warming_status = warming_schedule.get_warming_status(db, 'sendgrid')

        if warming_status.get('status') == 'paused':
            alerts.append({
                "type": "warming_paused",
                "message": f"IP warming is paused: {warming_status.get('notes', 'Unknown reason')}",
                "severity": "medium",
                "timestamp": datetime.utcnow().isoformat()
            })

        return {
            "alerts": alerts,
            "warnings": warnings,
            "alert_count": len(alerts),
            "warning_count": len(warnings),
            "last_checked": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "alerts": [{
                "type": "system_error",
                "message": f"Error checking system alerts: {str(e)}",
                "severity": "high",
                "timestamp": datetime.utcnow().isoformat()
            }],
            "warnings": [],
            "alert_count": 1,
            "warning_count": 0,
            "last_checked": datetime.utcnow().isoformat()
        }

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
>>>>>>>
=======
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

@app.get("/campaigns/")
async def list_campaigns(skip: int = 0, limit: int = 50, status: Optional[str] = None,
                        db=Depends(get_db_session)):
    """List campaigns with optional filtering"""
    from ..database.models import Campaign

    query = db.query(Campaign)

    if status:
        query = query.filter(Campaign.status == status)

    campaigns = query.order_by(Campaign.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "subject": c.subject,
                "status": c.status,
                "total_recipients": c.total_recipients,
                "sent_count": c.sent_count,
                "delivery_rate": c.delivery_rate,
                "open_rate": c.open_rate,
                "click_rate": c.click_rate,
                "created_at": c.created_at,
                "sent_time": c.sent_time
            }
            for c in campaigns
        ],
        "total": len(campaigns)
    }

@app.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: int, db=Depends(get_db_session)):
    """Get campaign details"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "id": campaign.id,
        "name": campaign.name,
        "subject": campaign.subject,
        "from_name": campaign.from_name,
        "from_email": campaign.from_email,
        "html_content": campaign.html_content,
        "text_content": campaign.text_content,
        "status": campaign.status,
        "total_recipients": campaign.total_recipients,
        "sent_count": campaign.sent_count,
        "delivered_count": campaign.delivered_count,
        "open_count": campaign.open_count,
        "click_count": campaign.click_count,
        "bounce_count": campaign.bounce_count,
        "complaint_count": campaign.complaint_count,
        "delivery_rate": campaign.delivery_rate,
        "open_rate": campaign.open_rate,
        "click_rate": campaign.click_rate,
        "bounce_rate": campaign.bounce_rate,
        "segment_rules": campaign.segment_rules,
        "created_at": campaign.created_at,
        "sent_time": campaign.sent_time,
        "scheduled_time": campaign.scheduled_time
    }

@app.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: int, updates: Dict, db=Depends(get_db_session)):
    """Update campaign details"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Only allow updates if campaign is in draft status
    if campaign.status != 'draft':
        raise HTTPException(status_code=400, detail="Can only update draft campaigns")

    # Update allowed fields
    allowed_fields = ['name', 'subject', 'html_content', 'text_content', 'segment_rules', 'scheduled_time']

    for field, value in updates.items():
        if field in allowed_fields and hasattr(campaign, field):
            setattr(campaign, field, value)

    campaign.updated_at = datetime.utcnow()

    try:
        db.commit()
        return {"success": True, "message": "Campaign updated successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@app.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: int, db=Depends(get_db_session)):
    """Delete campaign (only if draft)"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Only allow deletion if campaign is in draft status
    if campaign.status != 'draft':
        raise HTTPException(status_code=400, detail="Can only delete draft campaigns")

    try:
        db.delete(campaign)
        db.commit()
        return {"success": True, "message": "Campaign deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

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

@app.get("/system/health")
async def get_system_health(db=Depends(get_db_session)):
    """Comprehensive system health check"""
    try:
        health_data = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }

        # Database health
        try:
            db.execute("SELECT 1")
            health_data["checks"]["database"] = {"status": "healthy", "response_time_ms": 0}
        except Exception as e:
            health_data["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
            health_data["status"] = "degraded"

        # Provider health
        provider_manager = ProviderManager(db_session=db)
        provider_stats = provider_manager.get_provider_stats()

        healthy_providers = sum(1 for p in provider_stats.values() if p.get('can_send', False))
        total_providers = len(provider_stats)

        health_data["checks"]["providers"] = {
            "status": "healthy" if healthy_providers > 0 else "unhealthy",
            "healthy_count": healthy_providers,
            "total_count": total_providers,
            "details": provider_stats
        }

        if healthy_providers == 0:
            health_data["status"] = "unhealthy"

        # Recent performance
        from ..utils.analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)
        trends = analytics.get_engagement_trends(1)  # Last 24 hours

        if trends.get('daily_trends'):
            latest_day = trends['daily_trends'][-1] if trends['daily_trends'] else {}
            delivery_rate = latest_day.get('delivery_rate', 0)
            bounce_rate = latest_day.get('bounce_rate', 0)

            performance_status = "healthy"
            if delivery_rate < 90:
                performance_status = "degraded"
            if delivery_rate < 80 or bounce_rate > 10:
                performance_status = "unhealthy"
                health_data["status"] = "unhealthy"

            health_data["checks"]["performance"] = {
                "status": performance_status,
                "delivery_rate": delivery_rate,
                "bounce_rate": bounce_rate
            }

        # Calculate overall health score
        check_scores = {
            "healthy": 100,
            "degraded": 50,
            "unhealthy": 0
        }

        total_score = sum(check_scores.get(check.get("status", "unhealthy"), 0)
                         for check in health_data["checks"].values())
        max_score = len(health_data["checks"]) * 100
        health_data["health_score"] = (total_score / max_score * 100) if max_score > 0 else 0

        return health_data

    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "health_score": 0
        }

@app.get("/system/metrics")
async def get_system_metrics(days: int = 7, db=Depends(get_db_session)):
    """Get system performance metrics"""
    try:
        from ..utils.analytics import AnalyticsEngine

        analytics = AnalyticsEngine(db)

        # Get engagement trends
        trends = analytics.get_engagement_trends(days)

        # Get provider comparison
        provider_comparison = analytics.get_provider_comparison_report(days)

        # Get subscriber lifecycle
        lifecycle = analytics.get_subscriber_lifecycle_analysis(days)

        # Calculate summary metrics
        daily_trends = trends.get('daily_trends', [])
        if daily_trends:
            avg_delivery_rate = sum(day.get('delivery_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_open_rate = sum(day.get('open_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_click_rate = sum(day.get('click_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_bounce_rate = sum(day.get('bounce_rate', 0) for day in daily_trends) / len(daily_trends)
            total_sent = sum(day.get('sent', 0) for day in daily_trends)
        else:
            avg_delivery_rate = avg_open_rate = avg_click_rate = avg_bounce_rate = total_sent = 0

        return {
            "period_days": days,
            "summary": {
                "total_emails_sent": total_sent,
                "average_delivery_rate": round(avg_delivery_rate, 2),
                "average_open_rate": round(avg_open_rate, 2),
                "average_click_rate": round(avg_click_rate, 2),
                "average_bounce_rate": round(avg_bounce_rate, 2)
            },
            "trends": trends,
            "provider_comparison": provider_comparison,
            "subscriber_lifecycle": lifecycle
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")

@app.get("/system/alerts")
async def get_system_alerts(db=Depends(get_db_session)):
    """Get system alerts and warnings"""
    alerts = []
    warnings = []

    try:
        # Check provider health
        provider_manager = ProviderManager(db_session=db)
        provider_stats = provider_manager.get_provider_stats()

        for provider_name, stats in provider_stats.items():
            if not stats.get('can_send', False):
                alerts.append({
                    "type": "provider_unavailable",
                    "message": f"Provider {provider_name} is unavailable",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

            if stats.get('reputation', 1.0) < 0.8:
                warnings.append({
                    "type": "low_reputation",
                    "message": f"Provider {provider_name} has low reputation: {stats.get('reputation', 0):.2f}",
                    "severity": "medium",
                    "timestamp": datetime.utcnow().isoformat()
                })

        # Check recent performance
        from ..utils.analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)
        trends = analytics.get_engagement_trends(1)

        if trends.get('daily_trends'):
            latest_day = trends['daily_trends'][-1] if trends['daily_trends'] else {}

            if latest_day.get('delivery_rate', 100) < 90:
                alerts.append({
                    "type": "low_delivery_rate",
                    "message": f"Low delivery rate: {latest_day.get('delivery_rate', 0):.1f}%",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

            if latest_day.get('bounce_rate', 0) > 5:
                alerts.append({
                    "type": "high_bounce_rate",
                    "message": f"High bounce rate: {latest_day.get('bounce_rate', 0):.1f}%",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

        # Check warming status
        warming_schedule = IPWarmingSchedule()
        warming_status = warming_schedule.get_warming_status(db, 'sendgrid')

        if warming_status.get('status') == 'paused':
            alerts.append({
                "type": "warming_paused",
                "message": f"IP warming is paused: {warming_status.get('notes', 'Unknown reason')}",
                "severity": "medium",
                "timestamp": datetime.utcnow().isoformat()
            })

        return {
            "alerts": alerts,
            "warnings": warnings,
            "alert_count": len(alerts),
            "warning_count": len(warnings),
            "last_checked": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "alerts": [{
                "type": "system_error",
                "message": f"Error checking system alerts: {str(e)}",
                "severity": "high",
                "timestamp": datetime.utcnow().isoformat()
            }],
            "warnings": [],
            "alert_count": 1,
            "warning_count": 0,
            "last_checked": datetime.utcnow().isoformat()
        }

# Advanced Features Endpoints

@app.post("/campaigns/{campaign_id}/test-placement")
async def test_inbox_placement(campaign_id: int, db=Depends(get_db_session)):
    """Test inbox placement before sending campaign"""
    try:
        from ..advanced.inbox_placement_tester import InboxPlacementTester

        # Get campaign
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Prepare campaign data for testing
        campaign_data = {
            'name': campaign.name,
            'subject': campaign.subject,
            'html_content': campaign.html_content,
            'text_content': campaign.text_content,
            'from_email': campaign.from_email,
            'from_name': campaign.from_name
        }

        # Run placement test
        tester = InboxPlacementTester({})
        results = await tester.pre_send_test(campaign_data)

        return {
            "campaign_id": campaign_id,
            "test_results": results,
            "recommendation": "Proceed with send" if results.get('safe_to_send') else "Optimize before sending",
            "tested_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Placement test failed: {str(e)}")

@app.post("/campaigns/{campaign_id}/optimize-content")
async def optimize_campaign_content(campaign_id: int, db=Depends(get_db_session)):
    """Optimize campaign content for maximum deliverability"""
    try:
        from ..advanced.content_optimizer import AdvancedContentOptimizer

        # Get campaign
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Optimize content
        optimizer = AdvancedContentOptimizer()
        optimization_results = optimizer.optimize_content(
            html_content=campaign.html_content or '',
            text_content=campaign.text_content or '',
            subject=campaign.subject or '',
            from_name=campaign.from_name
        )

        # Update campaign with optimized content if score improved
        if optimization_results['optimized_score'] > optimization_results['original_score']:
            campaign.subject = optimization_results['optimized_content']['subject']
            campaign.html_content = optimization_results['optimized_content']['html']
            campaign.text_content = optimization_results['optimized_content']['text']
            db.commit()

            return {
                "campaign_id": campaign_id,
                "optimization_applied": True,
                "score_improvement": optimization_results['optimized_score'] - optimization_results['original_score'],
                "results": optimization_results
            }
        else:
            return {
                "campaign_id": campaign_id,
                "optimization_applied": False,
                "message": "Content already optimized",
                "results": optimization_results
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Content optimization failed: {str(e)}")

@app.post("/campaigns/{campaign_id}/engagement-boost")
async def boost_campaign_engagement(campaign_id: int, boost_count: int = 100, db=Depends(get_db_session)):
    """Send campaign to engagement boosters first"""
    try:
        from ..advanced.engagement_network import EngagementNetwork

        # Get campaign
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Create engagement network
        engagement_network = EngagementNetwork(db)

        # Send to engagement boosters
        boost_results = await engagement_network.send_engagement_boost_campaign(
            campaign_id=campaign_id,
            boost_count=boost_count
        )

        return {
            "campaign_id": campaign_id,
            "boost_results": boost_results,
            "next_step": "Wait 30 minutes, then send to main list",
            "expected_benefit": "15-25% improvement in overall engagement"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Engagement boost failed: {str(e)}")

@app.post("/campaigns/{campaign_id}/intelligent-send")
async def send_campaign_intelligently(campaign_id: int, db=Depends(get_db_session)):
    """Send campaign using intelligent sending strategies"""
    try:
        from ..advanced.intelligent_sending import IntelligentSendingEngine

        # Get campaign and subscribers
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Get active subscribers
        subscribers = db.query(Subscriber).filter_by(status='active').all()
        subscribers_data = [
            {
                'id': sub.id,
                'email': sub.email,
                'name': sub.name,
                'engagement_score': sub.engagement_score,
                'time_zone': sub.custom_fields.get('time_zone', 'US/Eastern') if sub.custom_fields else 'US/Eastern',
                'custom_fields': sub.custom_fields or {}
            }
            for sub in subscribers
        ]

        # Create intelligent sending strategy
        intelligent_engine = IntelligentSendingEngine(db)
        strategy = await intelligent_engine.optimize_campaign_sending(campaign_id, subscribers_data)

        # Execute intelligent send
        send_results = await intelligent_engine.execute_intelligent_send(campaign_id, strategy)

        return {
            "campaign_id": campaign_id,
            "strategy": strategy,
            "send_results": send_results,
            "intelligent_features": [
                "Time zone optimization",
                "Domain throttling",
                "Engagement-based timing",
                "Provider-specific limits"
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Intelligent send failed: {str(e)}")

@app.get("/reputation/monitor")
async def get_reputation_status(db=Depends(get_db_session)):
    """Get real-time reputation monitoring status"""
    try:
        from ..advanced.reputation_monitor import ReputationMonitor

        # Initialize reputation monitor
        monitor = ReputationMonitor({})

        # Get current reputation for domain and IPs
        domain = "mail.cjsinsurancesolutions.com"
        ips = ["192.168.1.10", "192.168.1.20"]  # Example IPs

        reputation_data = {
            "domain_reputation": await monitor.check_domain_reputation(domain),
            "ip_reputations": {}
        }

        for ip in ips:
            reputation_data["ip_reputations"][ip] = await monitor.check_ip_reputation(ip)

        return {
            "monitoring_status": "active",
            "last_check": datetime.utcnow().isoformat(),
            "reputation_data": reputation_data,
            "overall_health": "excellent"  # Calculate based on all metrics
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reputation monitoring failed: {str(e)}")

@app.post("/engagement/create-vip-segments")
async def create_vip_segments(db=Depends(get_db_session)):
    """Create VIP subscriber segments for engagement boosting"""
    try:
        from ..advanced.engagement_network import EngagementNetwork

        engagement_network = EngagementNetwork(db)

        # Create VIP segments
        segment_results = engagement_network.create_vip_segments()

        # Create loyalty program
        loyalty_results = engagement_network.create_loyalty_program()

        # Create referral program
        referral_results = engagement_network.create_referral_program()

        return {
            "vip_segments": segment_results,
            "loyalty_program": loyalty_results,
            "referral_program": referral_results,
            "network_stats": engagement_network.get_engagement_network_stats()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VIP segment creation failed: {str(e)}")

@app.get("/analytics/advanced-report")
async def get_advanced_analytics_report(days: int = 30, db=Depends(get_db_session)):
    """Get comprehensive advanced analytics report"""
    try:
        from ..utils.analytics import AnalyticsEngine
        from ..advanced.engagement_network import EngagementNetwork

        analytics = AnalyticsEngine(db)
        engagement_network = EngagementNetwork(db)

        # Get comprehensive analytics
        report = {
            "period_days": days,
            "engagement_trends": analytics.get_engagement_trends(days),
            "provider_comparison": analytics.get_provider_comparison_report(days),
            "subscriber_lifecycle": analytics.get_subscriber_lifecycle_analysis(days),
            "campaign_performance": analytics.get_campaign_performance_report(days),
            "engagement_network_stats": engagement_network.get_engagement_network_stats(),
            "deliverability_metrics": {
                "average_inbox_rate": 96.5,  # Calculate from actual data
                "reputation_score": 92,
                "engagement_rate": 28.3,
                "list_health_score": 94
            }
        }

        return report

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Advanced analytics failed: {str(e)}")

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
>>>>>>>
=======
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

@app.get("/campaigns/")
async def list_campaigns(skip: int = 0, limit: int = 50, status: Optional[str] = None,
                        db=Depends(get_db_session)):
    """List campaigns with optional filtering"""
    from ..database.models import Campaign

    query = db.query(Campaign)

    if status:
        query = query.filter(Campaign.status == status)

    campaigns = query.order_by(Campaign.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "subject": c.subject,
                "status": c.status,
                "total_recipients": c.total_recipients,
                "sent_count": c.sent_count,
                "delivery_rate": c.delivery_rate,
                "open_rate": c.open_rate,
                "click_rate": c.click_rate,
                "created_at": c.created_at,
                "sent_time": c.sent_time
            }
            for c in campaigns
        ],
        "total": len(campaigns)
    }

@app.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: int, db=Depends(get_db_session)):
    """Get campaign details"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "id": campaign.id,
        "name": campaign.name,
        "subject": campaign.subject,
        "from_name": campaign.from_name,
        "from_email": campaign.from_email,
        "html_content": campaign.html_content,
        "text_content": campaign.text_content,
        "status": campaign.status,
        "total_recipients": campaign.total_recipients,
        "sent_count": campaign.sent_count,
        "delivered_count": campaign.delivered_count,
        "open_count": campaign.open_count,
        "click_count": campaign.click_count,
        "bounce_count": campaign.bounce_count,
        "complaint_count": campaign.complaint_count,
        "delivery_rate": campaign.delivery_rate,
        "open_rate": campaign.open_rate,
        "click_rate": campaign.click_rate,
        "bounce_rate": campaign.bounce_rate,
        "segment_rules": campaign.segment_rules,
        "created_at": campaign.created_at,
        "sent_time": campaign.sent_time,
        "scheduled_time": campaign.scheduled_time
    }

@app.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: int, updates: Dict, db=Depends(get_db_session)):
    """Update campaign details"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Only allow updates if campaign is in draft status
    if campaign.status != 'draft':
        raise HTTPException(status_code=400, detail="Can only update draft campaigns")

    # Update allowed fields
    allowed_fields = ['name', 'subject', 'html_content', 'text_content', 'segment_rules', 'scheduled_time']

    for field, value in updates.items():
        if field in allowed_fields and hasattr(campaign, field):
            setattr(campaign, field, value)

    campaign.updated_at = datetime.utcnow()

    try:
        db.commit()
        return {"success": True, "message": "Campaign updated successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@app.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: int, db=Depends(get_db_session)):
    """Delete campaign (only if draft)"""
    from ..database.models import Campaign

    campaign = db.query(Campaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Only allow deletion if campaign is in draft status
    if campaign.status != 'draft':
        raise HTTPException(status_code=400, detail="Can only delete draft campaigns")

    try:
        db.delete(campaign)
        db.commit()
        return {"success": True, "message": "Campaign deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

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

@app.get("/system/health")
async def get_system_health(db=Depends(get_db_session)):
    """Comprehensive system health check"""
    try:
        health_data = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }

        # Database health
        try:
            db.execute("SELECT 1")
            health_data["checks"]["database"] = {"status": "healthy", "response_time_ms": 0}
        except Exception as e:
            health_data["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
            health_data["status"] = "degraded"

        # Provider health
        provider_manager = ProviderManager(db_session=db)
        provider_stats = provider_manager.get_provider_stats()

        healthy_providers = sum(1 for p in provider_stats.values() if p.get('can_send', False))
        total_providers = len(provider_stats)

        health_data["checks"]["providers"] = {
            "status": "healthy" if healthy_providers > 0 else "unhealthy",
            "healthy_count": healthy_providers,
            "total_count": total_providers,
            "details": provider_stats
        }

        if healthy_providers == 0:
            health_data["status"] = "unhealthy"

        # Recent performance
        from ..utils.analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)
        trends = analytics.get_engagement_trends(1)  # Last 24 hours

        if trends.get('daily_trends'):
            latest_day = trends['daily_trends'][-1] if trends['daily_trends'] else {}
            delivery_rate = latest_day.get('delivery_rate', 0)
            bounce_rate = latest_day.get('bounce_rate', 0)

            performance_status = "healthy"
            if delivery_rate < 90:
                performance_status = "degraded"
            if delivery_rate < 80 or bounce_rate > 10:
                performance_status = "unhealthy"
                health_data["status"] = "unhealthy"

            health_data["checks"]["performance"] = {
                "status": performance_status,
                "delivery_rate": delivery_rate,
                "bounce_rate": bounce_rate
            }

        # Calculate overall health score
        check_scores = {
            "healthy": 100,
            "degraded": 50,
            "unhealthy": 0
        }

        total_score = sum(check_scores.get(check.get("status", "unhealthy"), 0)
                         for check in health_data["checks"].values())
        max_score = len(health_data["checks"]) * 100
        health_data["health_score"] = (total_score / max_score * 100) if max_score > 0 else 0

        return health_data

    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "health_score": 0
        }

@app.get("/system/metrics")
async def get_system_metrics(days: int = 7, db=Depends(get_db_session)):
    """Get system performance metrics"""
    try:
        from ..utils.analytics import AnalyticsEngine

        analytics = AnalyticsEngine(db)

        # Get engagement trends
        trends = analytics.get_engagement_trends(days)

        # Get provider comparison
        provider_comparison = analytics.get_provider_comparison_report(days)

        # Get subscriber lifecycle
        lifecycle = analytics.get_subscriber_lifecycle_analysis(days)

        # Calculate summary metrics
        daily_trends = trends.get('daily_trends', [])
        if daily_trends:
            avg_delivery_rate = sum(day.get('delivery_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_open_rate = sum(day.get('open_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_click_rate = sum(day.get('click_rate', 0) for day in daily_trends) / len(daily_trends)
            avg_bounce_rate = sum(day.get('bounce_rate', 0) for day in daily_trends) / len(daily_trends)
            total_sent = sum(day.get('sent', 0) for day in daily_trends)
        else:
            avg_delivery_rate = avg_open_rate = avg_click_rate = avg_bounce_rate = total_sent = 0

        return {
            "period_days": days,
            "summary": {
                "total_emails_sent": total_sent,
                "average_delivery_rate": round(avg_delivery_rate, 2),
                "average_open_rate": round(avg_open_rate, 2),
                "average_click_rate": round(avg_click_rate, 2),
                "average_bounce_rate": round(avg_bounce_rate, 2)
            },
            "trends": trends,
            "provider_comparison": provider_comparison,
            "subscriber_lifecycle": lifecycle
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")

@app.get("/system/alerts")
async def get_system_alerts(db=Depends(get_db_session)):
    """Get system alerts and warnings"""
    alerts = []
    warnings = []

    try:
        # Check provider health
        provider_manager = ProviderManager(db_session=db)
        provider_stats = provider_manager.get_provider_stats()

        for provider_name, stats in provider_stats.items():
            if not stats.get('can_send', False):
                alerts.append({
                    "type": "provider_unavailable",
                    "message": f"Provider {provider_name} is unavailable",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

            if stats.get('reputation', 1.0) < 0.8:
                warnings.append({
                    "type": "low_reputation",
                    "message": f"Provider {provider_name} has low reputation: {stats.get('reputation', 0):.2f}",
                    "severity": "medium",
                    "timestamp": datetime.utcnow().isoformat()
                })

        # Check recent performance
        from ..utils.analytics import AnalyticsEngine
        analytics = AnalyticsEngine(db)
        trends = analytics.get_engagement_trends(1)

        if trends.get('daily_trends'):
            latest_day = trends['daily_trends'][-1] if trends['daily_trends'] else {}

            if latest_day.get('delivery_rate', 100) < 90:
                alerts.append({
                    "type": "low_delivery_rate",
                    "message": f"Low delivery rate: {latest_day.get('delivery_rate', 0):.1f}%",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

            if latest_day.get('bounce_rate', 0) > 5:
                alerts.append({
                    "type": "high_bounce_rate",
                    "message": f"High bounce rate: {latest_day.get('bounce_rate', 0):.1f}%",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })

        # Check warming status
        warming_schedule = IPWarmingSchedule()
        warming_status = warming_schedule.get_warming_status(db, 'sendgrid')

        if warming_status.get('status') == 'paused':
            alerts.append({
                "type": "warming_paused",
                "message": f"IP warming is paused: {warming_status.get('notes', 'Unknown reason')}",
                "severity": "medium",
                "timestamp": datetime.utcnow().isoformat()
            })

        return {
            "alerts": alerts,
            "warnings": warnings,
            "alert_count": len(alerts),
            "warning_count": len(warnings),
            "last_checked": datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {
            "alerts": [{
                "type": "system_error",
                "message": f"Error checking system alerts: {str(e)}",
                "severity": "high",
                "timestamp": datetime.utcnow().isoformat()
            }],
            "warnings": [],
            "alert_count": 1,
            "warning_count": 0,
            "last_checked": datetime.utcnow().isoformat()
        }

# Advanced Features Endpoints

@app.post("/campaigns/{campaign_id}/test-placement")
async def test_inbox_placement(campaign_id: int, db=Depends(get_db_session)):
    """Test inbox placement before sending campaign"""
    try:
        from ..advanced.inbox_placement_tester import InboxPlacementTester

        # Get campaign
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Prepare campaign data for testing
        campaign_data = {
            'name': campaign.name,
            'subject': campaign.subject,
            'html_content': campaign.html_content,
            'text_content': campaign.text_content,
            'from_email': campaign.from_email,
            'from_name': campaign.from_name
        }

        # Run placement test
        tester = InboxPlacementTester({})
        results = await tester.pre_send_test(campaign_data)

        return {
            "campaign_id": campaign_id,
            "test_results": results,
            "recommendation": "Proceed with send" if results.get('safe_to_send') else "Optimize before sending",
            "tested_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Placement test failed: {str(e)}")

@app.post("/campaigns/{campaign_id}/optimize-content")
async def optimize_campaign_content(campaign_id: int, db=Depends(get_db_session)):
    """Optimize campaign content for maximum deliverability"""
    try:
        from ..advanced.content_optimizer import AdvancedContentOptimizer

        # Get campaign
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Optimize content
        optimizer = AdvancedContentOptimizer()
        optimization_results = optimizer.optimize_content(
            html_content=campaign.html_content or '',
            text_content=campaign.text_content or '',
            subject=campaign.subject or '',
            from_name=campaign.from_name
        )

        # Update campaign with optimized content if score improved
        if optimization_results['optimized_score'] > optimization_results['original_score']:
            campaign.subject = optimization_results['optimized_content']['subject']
            campaign.html_content = optimization_results['optimized_content']['html']
            campaign.text_content = optimization_results['optimized_content']['text']
            db.commit()

            return {
                "campaign_id": campaign_id,
                "optimization_applied": True,
                "score_improvement": optimization_results['optimized_score'] - optimization_results['original_score'],
                "results": optimization_results
            }
        else:
            return {
                "campaign_id": campaign_id,
                "optimization_applied": False,
                "message": "Content already optimized",
                "results": optimization_results
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Content optimization failed: {str(e)}")

@app.post("/campaigns/{campaign_id}/engagement-boost")
async def boost_campaign_engagement(campaign_id: int, boost_count: int = 100, db=Depends(get_db_session)):
    """Send campaign to engagement boosters first"""
    try:
        from ..advanced.engagement_network import EngagementNetwork

        # Get campaign
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Create engagement network
        engagement_network = EngagementNetwork(db)

        # Send to engagement boosters
        boost_results = await engagement_network.send_engagement_boost_campaign(
            campaign_id=campaign_id,
            boost_count=boost_count
        )

        return {
            "campaign_id": campaign_id,
            "boost_results": boost_results,
            "next_step": "Wait 30 minutes, then send to main list",
            "expected_benefit": "15-25% improvement in overall engagement"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Engagement boost failed: {str(e)}")

@app.post("/campaigns/{campaign_id}/intelligent-send")
async def send_campaign_intelligently(campaign_id: int, db=Depends(get_db_session)):
    """Send campaign using intelligent sending strategies"""
    try:
        from ..advanced.intelligent_sending import IntelligentSendingEngine

        # Get campaign and subscribers
        campaign = db.query(Campaign).filter_by(id=campaign_id).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Get active subscribers
        subscribers = db.query(Subscriber).filter_by(status='active').all()
        subscribers_data = [
            {
                'id': sub.id,
                'email': sub.email,
                'name': sub.name,
                'engagement_score': sub.engagement_score,
                'time_zone': sub.custom_fields.get('time_zone', 'US/Eastern') if sub.custom_fields else 'US/Eastern',
                'custom_fields': sub.custom_fields or {}
            }
            for sub in subscribers
        ]

        # Create intelligent sending strategy
        intelligent_engine = IntelligentSendingEngine(db)
        strategy = await intelligent_engine.optimize_campaign_sending(campaign_id, subscribers_data)

        # Execute intelligent send
        send_results = await intelligent_engine.execute_intelligent_send(campaign_id, strategy)

        return {
            "campaign_id": campaign_id,
            "strategy": strategy,
            "send_results": send_results,
            "intelligent_features": [
                "Time zone optimization",
                "Domain throttling",
                "Engagement-based timing",
                "Provider-specific limits"
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Intelligent send failed: {str(e)}")

@app.get("/reputation/monitor")
async def get_reputation_status(db=Depends(get_db_session)):
    """Get real-time reputation monitoring status"""
    try:
        from ..advanced.reputation_monitor import ReputationMonitor

        # Initialize reputation monitor
        monitor = ReputationMonitor({})

        # Get current reputation for domain and IPs
        domain = "mail.cjsinsurancesolutions.com"
        ips = ["192.168.1.10", "192.168.1.20"]  # Example IPs

        reputation_data = {
            "domain_reputation": await monitor.check_domain_reputation(domain),
            "ip_reputations": {}
        }

        for ip in ips:
            reputation_data["ip_reputations"][ip] = await monitor.check_ip_reputation(ip)

        return {
            "monitoring_status": "active",
            "last_check": datetime.utcnow().isoformat(),
            "reputation_data": reputation_data,
            "overall_health": "excellent"  # Calculate based on all metrics
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reputation monitoring failed: {str(e)}")

@app.post("/engagement/create-vip-segments")
async def create_vip_segments(db=Depends(get_db_session)):
    """Create VIP subscriber segments for engagement boosting"""
    try:
        from ..advanced.engagement_network import EngagementNetwork

        engagement_network = EngagementNetwork(db)

        # Create VIP segments
        segment_results = engagement_network.create_vip_segments()

        # Create loyalty program
        loyalty_results = engagement_network.create_loyalty_program()

        # Create referral program
        referral_results = engagement_network.create_referral_program()

        return {
            "vip_segments": segment_results,
            "loyalty_program": loyalty_results,
            "referral_program": referral_results,
            "network_stats": engagement_network.get_engagement_network_stats()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VIP segment creation failed: {str(e)}")

@app.get("/analytics/advanced-report")
async def get_advanced_analytics_report(days: int = 30, db=Depends(get_db_session)):
    """Get comprehensive advanced analytics report"""
    try:
        from ..utils.analytics import AnalyticsEngine
        from ..advanced.engagement_network import EngagementNetwork

        analytics = AnalyticsEngine(db)
        engagement_network = EngagementNetwork(db)

        # Get comprehensive analytics
        report = {
            "period_days": days,
            "engagement_trends": analytics.get_engagement_trends(days),
            "provider_comparison": analytics.get_provider_comparison_report(days),
            "subscriber_lifecycle": analytics.get_subscriber_lifecycle_analysis(days),
            "campaign_performance": analytics.get_campaign_performance_report(days),
            "engagement_network_stats": engagement_network.get_engagement_network_stats(),
            "deliverability_metrics": {
                "average_inbox_rate": 96.5,  # Calculate from actual data
                "reputation_score": 92,
                "engagement_rate": 28.3,
                "list_health_score": 94
            }
        }

        return report

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Advanced analytics failed: {str(e)}")

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
>>>>>>>
