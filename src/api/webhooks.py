"""
Real-time Webhook Processing for Email Delivery Events
Handles webhooks from SendGrid, Amazon SES, and Postmark
"""

import json
import logging
import hashlib
import hmac
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

from ..database.async_models import get_async_db

# Configure logging
logger = logging.getLogger(__name__)

# Create webhook router
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Pydantic models for webhook events
class DeliveryEvent(BaseModel):
    message_id: str
    event_type: str
    timestamp: datetime
    email: str
    campaign_id: Optional[int] = None
    esp_provider: str
    details: Dict[str, Any] = {}

class WebhookResponse(BaseModel):
    success: bool
    processed_events: int
    message: str

# Database operations for delivery events
async def store_delivery_event(db, event: DeliveryEvent):
    """Store delivery event in database"""
    try:
        await db.execute_update("""
            INSERT INTO delivery_events 
            (message_id, event_type, timestamp, email, campaign_id, esp_provider, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.message_id,
            event.event_type,
            event.timestamp,
            event.email,
            event.campaign_id,
            event.esp_provider,
            json.dumps(event.details),
            datetime.utcnow()
        ))
        
        # Update subscriber engagement based on event type
        if event.event_type in ['open', 'click']:
            await update_subscriber_engagement(db, event.email, event.event_type)
            
        # Update campaign stats
        if event.campaign_id:
            await update_campaign_stats(db, event.campaign_id, event.event_type)
            
        logger.info(f"Stored {event.event_type} event for {event.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to store delivery event: {str(e)}")
        return False

async def update_subscriber_engagement(db, email: str, event_type: str):
    """Update subscriber engagement score"""
    try:
        # Get current engagement score
        result = await db.execute_query(
            "SELECT engagement_score FROM subscribers WHERE email = ?", 
            (email,)
        )
        
        if result:
            current_score = result[0].get('engagement_score', 0)
            
            # Calculate new score based on event type
            score_increment = {'open': 1, 'click': 3}.get(event_type, 0)
            new_score = min(100, current_score + score_increment)
            
            # Update subscriber
            await db.execute_update("""
                UPDATE subscribers 
                SET engagement_score = ?, last_engagement = ?
                WHERE email = ?
            """, (new_score, datetime.utcnow(), email))
            
    except Exception as e:
        logger.error(f"Failed to update subscriber engagement: {str(e)}")

async def update_campaign_stats(db, campaign_id: int, event_type: str):
    """Update campaign statistics"""
    try:
        # Update campaign stats based on event type
        column_map = {
            'delivered': 'delivered_count',
            'open': 'opened_count', 
            'click': 'clicked_count',
            'bounce': 'bounced_count',
            'complaint': 'complained_count'
        }
        
        column = column_map.get(event_type)
        if column:
            await db.execute_update(f"""
                UPDATE campaigns 
                SET {column} = {column} + 1, updated_at = ?
                WHERE id = ?
            """, (datetime.utcnow(), campaign_id))
            
    except Exception as e:
        logger.error(f"Failed to update campaign stats: {str(e)}")

# SendGrid webhook handler
@webhook_router.post("/sendgrid", response_model=WebhookResponse)
async def process_sendgrid_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db=Depends(get_async_db)
):
    """Process SendGrid webhook events"""
    try:
        # Verify webhook signature (optional but recommended)
        # signature = request.headers.get('X-Twilio-Email-Event-Webhook-Signature')
        # if not verify_sendgrid_signature(await request.body(), signature):
        #     raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse webhook payload
        events = await request.json()
        if not isinstance(events, list):
            events = [events]
        
        processed_count = 0
        
        for event_data in events:
            try:
                # Extract event information
                event = DeliveryEvent(
                    message_id=event_data.get('sg_message_id', ''),
                    event_type=event_data.get('event', 'unknown'),
                    timestamp=datetime.fromtimestamp(event_data.get('timestamp', 0)),
                    email=event_data.get('email', ''),
                    campaign_id=event_data.get('campaign_id'),
                    esp_provider='sendgrid',
                    details={
                        'user_agent': event_data.get('useragent', ''),
                        'ip_address': event_data.get('ip', ''),
                        'url': event_data.get('url', ''),
                        'reason': event_data.get('reason', ''),
                        'bounce_type': event_data.get('type', ''),
                        'raw_event': event_data
                    }
                )
                
                # Store event in background
                background_tasks.add_task(store_delivery_event, db, event)
                processed_count += 1
                
            except Exception as e:
                logger.error(f"Failed to process SendGrid event: {str(e)}")
                continue
        
        return WebhookResponse(
            success=True,
            processed_events=processed_count,
            message=f"Processed {processed_count} SendGrid events"
        )
        
    except Exception as e:
        logger.error(f"SendGrid webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process webhook")

# Amazon SES webhook handler
@webhook_router.post("/amazon-ses", response_model=WebhookResponse)
async def process_amazon_ses_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db=Depends(get_async_db)
):
    """Process Amazon SES webhook events (SNS notifications)"""
    try:
        # Parse SNS notification
        sns_data = await request.json()
        
        # Handle SNS subscription confirmation
        if sns_data.get('Type') == 'SubscriptionConfirmation':
            # In production, you'd confirm the subscription
            logger.info("SNS subscription confirmation received")
            return WebhookResponse(
                success=True,
                processed_events=0,
                message="SNS subscription confirmation"
            )
        
        # Process notification message
        if sns_data.get('Type') == 'Notification':
            message = json.loads(sns_data.get('Message', '{}'))
            
            # Extract event information
            event_type = message.get('eventType', 'unknown')
            mail_data = message.get('mail', {})
            
            event = DeliveryEvent(
                message_id=mail_data.get('messageId', ''),
                event_type=event_type.lower(),
                timestamp=datetime.fromisoformat(mail_data.get('timestamp', datetime.utcnow().isoformat())),
                email=mail_data.get('destination', [''])[0] if mail_data.get('destination') else '',
                esp_provider='amazon_ses',
                details={
                    'source': mail_data.get('source', ''),
                    'sending_account_id': message.get('mail', {}).get('sendingAccountId', ''),
                    'raw_event': message
                }
            )
            
            # Store event in background
            background_tasks.add_task(store_delivery_event, db, event)
            
            return WebhookResponse(
                success=True,
                processed_events=1,
                message="Processed Amazon SES event"
            )
        
        return WebhookResponse(
            success=True,
            processed_events=0,
            message="No events to process"
        )
        
    except Exception as e:
        logger.error(f"Amazon SES webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process webhook")

# Postmark webhook handler
@webhook_router.post("/postmark", response_model=WebhookResponse)
async def process_postmark_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db=Depends(get_async_db)
):
    """Process Postmark webhook events"""
    try:
        # Parse webhook payload
        event_data = await request.json()
        
        # Map Postmark event types to our standard types
        event_type_map = {
            'Delivery': 'delivered',
            'Open': 'open',
            'Click': 'click',
            'Bounce': 'bounce',
            'SpamComplaint': 'complaint',
            'Unsubscribe': 'unsubscribe'
        }
        
        postmark_event_type = event_data.get('RecordType', 'unknown')
        event_type = event_type_map.get(postmark_event_type, 'unknown')
        
        event = DeliveryEvent(
            message_id=event_data.get('MessageID', ''),
            event_type=event_type,
            timestamp=datetime.fromisoformat(event_data.get('DeliveredAt', datetime.utcnow().isoformat())),
            email=event_data.get('Email', ''),
            esp_provider='postmark',
            details={
                'user_agent': event_data.get('UserAgent', ''),
                'ip_address': event_data.get('IP', ''),
                'original_link': event_data.get('OriginalLink', ''),
                'bounce_type': event_data.get('Type', ''),
                'description': event_data.get('Description', ''),
                'raw_event': event_data
            }
        )
        
        # Store event in background
        background_tasks.add_task(store_delivery_event, db, event)
        
        return WebhookResponse(
            success=True,
            processed_events=1,
            message="Processed Postmark event"
        )
        
    except Exception as e:
        logger.error(f"Postmark webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process webhook")

# Webhook status endpoint
@webhook_router.get("/status")
async def webhook_status():
    """Get webhook endpoint status"""
    return {
        "status": "operational",
        "endpoints": [
            "/webhooks/sendgrid",
            "/webhooks/amazon-ses", 
            "/webhooks/postmark"
        ],
        "last_updated": datetime.utcnow().isoformat()
    }
