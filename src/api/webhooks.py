# src/api/webhooks.py
from fastapi import APIRouter, Request, HTTPException, Depends
from typing import Dict, List
import json
import hmac
import hashlib
from datetime import datetime

from ..database.models import get_db
from ..database.engagement_tracker import EngagementTracker

# Create webhook router
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

def get_db_session():
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()

def verify_sendgrid_signature(payload: bytes, signature: str, webhook_key: str) -> bool:
    """Verify SendGrid webhook signature"""
    try:
        expected_signature = hmac.new(
            webhook_key.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    except Exception:
        return False

def verify_postmark_signature(payload: bytes, signature: str, webhook_key: str) -> bool:
    """Verify Postmark webhook signature"""
    try:
        expected_signature = hmac.new(
            webhook_key.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    except Exception:
        return False

@webhook_router.post("/sendgrid")
async def sendgrid_webhook(request: Request, db=Depends(get_db_session)):
    """Handle SendGrid webhook events"""
    
    # Get raw payload for signature verification
    payload = await request.body()
    
    # Verify signature (optional but recommended)
    signature = request.headers.get('X-Twilio-Email-Event-Webhook-Signature')
    webhook_key = "your_sendgrid_webhook_key"  # Should be in config
    
    # if signature and not verify_sendgrid_signature(payload, signature, webhook_key):
    #     raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        events = json.loads(payload)
        tracker = EngagementTracker(db)
        
        processed_events = []
        
        for event in events:
            event_type = event.get('event')
            message_id = event.get('sg_message_id')
            email = event.get('email')
            timestamp = event.get('timestamp')
            
            success = False
            
            if event_type == 'delivered':
                success = tracker.track_delivery(message_id=message_id)
                
            elif event_type == 'open':
                success = tracker.track_open(
                    message_id=message_id,
                    user_agent=event.get('useragent'),
                    ip_address=event.get('ip')
                )
                
            elif event_type == 'click':
                success = tracker.track_click(
                    message_id=message_id,
                    clicked_url=event.get('url'),
                    user_agent=event.get('useragent'),
                    ip_address=event.get('ip')
                )
                
            elif event_type in ['bounce', 'blocked']:
                bounce_type = 'hard' if event.get('type') == 'bounce' else 'blocked'
                success = tracker.track_bounce(
                    message_id=message_id,
                    bounce_type=bounce_type,
                    bounce_reason=event.get('reason')
                )
                
            elif event_type == 'spamreport':
                success = tracker.track_complaint(
                    message_id=message_id,
                    complaint_type='spam'
                )
                
            elif event_type == 'unsubscribe':
                success = tracker.track_unsubscribe(
                    message_id=message_id,
                    email=email
                )
            
            processed_events.append({
                'event_type': event_type,
                'message_id': message_id,
                'email': email,
                'processed': success,
                'timestamp': timestamp
            })
        
        return {
            "success": True,
            "processed_events": len(processed_events),
            "events": processed_events
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing SendGrid webhook: {str(e)}")

@webhook_router.post("/amazon-ses")
async def amazon_ses_webhook(request: Request, db=Depends(get_db_session)):
    """Handle Amazon SES webhook events (SNS notifications)"""
    
    try:
        payload = await request.json()
        tracker = EngagementTracker(db)
        
        # Handle SNS message confirmation
        if payload.get('Type') == 'SubscriptionConfirmation':
            # In production, you would confirm the subscription
            return {"message": "Subscription confirmation received"}
        
        # Handle SNS notifications
        if payload.get('Type') == 'Notification':
            message = json.loads(payload.get('Message', '{}'))
            
            event_type = message.get('eventType')
            mail = message.get('mail', {})
            message_id = mail.get('messageId')
            
            success = False
            
            if event_type == 'delivery':
                success = tracker.track_delivery(message_id=message_id)
                
            elif event_type == 'bounce':
                bounce = message.get('bounce', {})
                bounce_type = bounce.get('bounceType', 'hard').lower()
                bounce_reason = bounce.get('bouncedRecipients', [{}])[0].get('diagnosticCode')
                
                success = tracker.track_bounce(
                    message_id=message_id,
                    bounce_type=bounce_type,
                    bounce_reason=bounce_reason
                )
                
            elif event_type == 'complaint':
                success = tracker.track_complaint(
                    message_id=message_id,
                    complaint_type='spam'
                )
            
            return {
                "success": True,
                "event_type": event_type,
                "message_id": message_id,
                "processed": success
            }
        
        return {"message": "Unknown message type"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing SES webhook: {str(e)}")

@webhook_router.post("/postmark")
async def postmark_webhook(request: Request, db=Depends(get_db_session)):
    """Handle Postmark webhook events"""
    
    # Get raw payload for signature verification
    payload = await request.body()
    
    # Verify signature (optional but recommended)
    signature = request.headers.get('X-Postmark-Signature')
    webhook_key = "your_postmark_webhook_key"  # Should be in config
    
    # if signature and not verify_postmark_signature(payload, signature, webhook_key):
    #     raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        event = json.loads(payload)
        tracker = EngagementTracker(db)
        
        record_type = event.get('RecordType')
        message_id = event.get('MessageID')
        email = event.get('Email')
        
        success = False
        
        if record_type == 'Delivery':
            success = tracker.track_delivery(message_id=message_id)
            
        elif record_type == 'Open':
            success = tracker.track_open(
                message_id=message_id,
                user_agent=event.get('UserAgent'),
                ip_address=event.get('Client', {}).get('IP')
            )
            
        elif record_type == 'Click':
            success = tracker.track_click(
                message_id=message_id,
                clicked_url=event.get('OriginalLink'),
                user_agent=event.get('UserAgent'),
                ip_address=event.get('Client', {}).get('IP')
            )
            
        elif record_type == 'Bounce':
            bounce_type = 'hard' if event.get('Type') == 'HardBounce' else 'soft'
            success = tracker.track_bounce(
                message_id=message_id,
                bounce_type=bounce_type,
                bounce_reason=event.get('Description')
            )
            
        elif record_type == 'SpamComplaint':
            success = tracker.track_complaint(
                message_id=message_id,
                complaint_type='spam'
            )
            
        elif record_type == 'SubscriptionChange':
            if event.get('SuppressSending'):
                success = tracker.track_unsubscribe(
                    message_id=message_id,
                    email=email
                )
        
        return {
            "success": True,
            "record_type": record_type,
            "message_id": message_id,
            "email": email,
            "processed": success
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing Postmark webhook: {str(e)}")

@webhook_router.post("/generic")
async def generic_webhook(request: Request, db=Depends(get_db_session)):
    """Handle generic webhook events for testing"""
    
    try:
        event = await request.json()
        tracker = EngagementTracker(db)
        
        event_type = event.get('event_type')
        message_id = event.get('message_id')
        engagement_id = event.get('engagement_id')
        
        success = False
        
        if event_type == 'delivery':
            success = tracker.track_delivery(
                engagement_id=engagement_id,
                message_id=message_id
            )
            
        elif event_type == 'open':
            success = tracker.track_open(
                engagement_id=engagement_id,
                message_id=message_id,
                user_agent=event.get('user_agent'),
                ip_address=event.get('ip_address')
            )
            
        elif event_type == 'click':
            success = tracker.track_click(
                engagement_id=engagement_id,
                message_id=message_id,
                clicked_url=event.get('clicked_url'),
                user_agent=event.get('user_agent'),
                ip_address=event.get('ip_address')
            )
            
        elif event_type == 'bounce':
            success = tracker.track_bounce(
                engagement_id=engagement_id,
                message_id=message_id,
                bounce_type=event.get('bounce_type', 'hard'),
                bounce_reason=event.get('bounce_reason')
            )
            
        elif event_type == 'complaint':
            success = tracker.track_complaint(
                engagement_id=engagement_id,
                message_id=message_id,
                complaint_type=event.get('complaint_type', 'spam')
            )
            
        elif event_type == 'unsubscribe':
            success = tracker.track_unsubscribe(
                engagement_id=engagement_id,
                message_id=message_id,
                email=event.get('email')
            )
        
        return {
            "success": True,
            "event_type": event_type,
            "processed": success,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing generic webhook: {str(e)}")

# Webhook status endpoint
@webhook_router.get("/status")
async def webhook_status():
    """Get webhook endpoint status"""
    return {
        "status": "operational",
        "endpoints": {
            "sendgrid": "/webhooks/sendgrid",
            "amazon_ses": "/webhooks/amazon-ses", 
            "postmark": "/webhooks/postmark",
            "generic": "/webhooks/generic"
        },
        "supported_events": [
            "delivery",
            "open", 
            "click",
            "bounce",
            "complaint",
            "unsubscribe"
        ]
    }
