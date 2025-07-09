# src/api/webhooks.py
from fastapi import APIRouter, Request, HTTPException, Depends
from typing import Dict, List
import json
import hmac
import hashlib
import os
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
    """Handle SendGrid webhook events with comprehensive processing"""

    # Get raw payload for signature verification
    payload = await request.body()

    # Verify signature (optional but recommended)
    signature = request.headers.get('X-Twilio-Email-Event-Webhook-Signature')
    webhook_key = os.getenv('SENDGRID_WEBHOOK_KEY')

    if webhook_key and signature:
        if not verify_sendgrid_signature(payload, signature, webhook_key):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        events = json.loads(payload)
        tracker = EngagementTracker(db)

        processed_events = []
        provider_stats = {'delivered': 0, 'bounced': 0, 'opened': 0, 'clicked': 0, 'complained': 0}

        for event in events:
            event_type = event.get('event')
            message_id = event.get('sg_message_id')
            email = event.get('email')
            timestamp = event.get('timestamp')

            success = False

            # Process different event types
            if event_type == 'delivered':
                success = tracker.track_delivery(message_id=message_id)
                if success:
                    provider_stats['delivered'] += 1

            elif event_type == 'open':
                success = tracker.track_open(
                    message_id=message_id,
                    user_agent=event.get('useragent'),
                    ip_address=event.get('ip')
                )
                if success:
                    provider_stats['opened'] += 1

            elif event_type == 'click':
                success = tracker.track_click(
                    message_id=message_id,
                    clicked_url=event.get('url'),
                    user_agent=event.get('useragent'),
                    ip_address=event.get('ip')
                )
                if success:
                    provider_stats['clicked'] += 1

            elif event_type in ['bounce', 'blocked', 'dropped']:
                # Determine bounce type
                bounce_type = 'hard'
                if event_type == 'blocked':
                    bounce_type = 'blocked'
                elif event.get('type') == 'soft':
                    bounce_type = 'soft'

                success = tracker.track_bounce(
                    message_id=message_id,
                    bounce_type=bounce_type,
                    bounce_reason=event.get('reason')
                )
                if success:
                    provider_stats['bounced'] += 1

            elif event_type == 'spamreport':
                success = tracker.track_complaint(
                    message_id=message_id,
                    complaint_type='spam'
                )
                if success:
                    provider_stats['complained'] += 1

            elif event_type == 'unsubscribe':
                success = tracker.track_unsubscribe(
                    message_id=message_id,
                    email=email
                )

            elif event_type == 'group_unsubscribe':
                success = tracker.track_unsubscribe(
                    message_id=message_id,
                    email=email
                )

            # Store additional event data
            event_data = {
                'event_type': event_type,
                'message_id': message_id,
                'email': email,
                'processed': success,
                'timestamp': timestamp,
                'raw_event': event  # Store full event for debugging
            }

            processed_events.append(event_data)

        # Update provider reputation based on events
        from ..core.provider_manager import ProviderManager
        provider_manager = ProviderManager(db_session=db)

        # Update reputation for each event type
        for event_type, count in provider_stats.items():
            for _ in range(count):
                provider_manager.update_reputation('sendgrid', event_type)

        return {
            "success": True,
            "processed_events": len(processed_events),
            "provider_stats": provider_stats,
            "events": processed_events[:10]  # Return first 10 for response size
        }

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing SendGrid webhook: {str(e)}")

@webhook_router.post("/amazon-ses")
async def amazon_ses_webhook(request: Request, db=Depends(get_db_session)):
    """Handle Amazon SES webhook events (SNS notifications) with comprehensive processing"""

    try:
        payload = await request.json()
        tracker = EngagementTracker(db)

        # Handle SNS message confirmation
        if payload.get('Type') == 'SubscriptionConfirmation':
            # In production, you would confirm the subscription automatically
            confirm_url = payload.get('SubscribeURL')
            if confirm_url:
                # You could auto-confirm here with requests.get(confirm_url)
                print(f"SNS Subscription confirmation URL: {confirm_url}")
            return {"message": "Subscription confirmation received", "confirm_url": confirm_url}

        # Handle SNS notifications
        if payload.get('Type') == 'Notification':
            message = json.loads(payload.get('Message', '{}'))

            event_type = message.get('eventType')
            mail = message.get('mail', {})
            message_id = mail.get('messageId')

            success = False
            provider_stats = {}

            if event_type == 'delivery':
                delivery = message.get('delivery', {})
                success = tracker.track_delivery(message_id=message_id)
                provider_stats['delivered'] = 1

            elif event_type == 'bounce':
                bounce = message.get('bounce', {})
                bounce_type = bounce.get('bounceType', 'Permanent').lower()
                bounce_subtype = bounce.get('bounceSubType', '')

                # Map SES bounce types to our system
                if bounce_type == 'permanent':
                    mapped_bounce_type = 'hard'
                elif bounce_type == 'transient':
                    mapped_bounce_type = 'soft'
                else:
                    mapped_bounce_type = 'hard'

                # Get bounce reason from recipients
                bounced_recipients = bounce.get('bouncedRecipients', [])
                bounce_reason = None
                if bounced_recipients:
                    bounce_reason = bounced_recipients[0].get('diagnosticCode') or bounced_recipients[0].get('status')

                success = tracker.track_bounce(
                    message_id=message_id,
                    bounce_type=mapped_bounce_type,
                    bounce_reason=f"{bounce_subtype}: {bounce_reason}" if bounce_reason else bounce_subtype
                )
                provider_stats['bounced'] = 1

            elif event_type == 'complaint':
                complaint = message.get('complaint', {})
                complaint_type = complaint.get('complaintFeedbackType', 'spam')

                success = tracker.track_complaint(
                    message_id=message_id,
                    complaint_type=complaint_type
                )
                provider_stats['complained'] = 1

            elif event_type == 'reject':
                # Handle SES rejects as hard bounces
                reject = message.get('reject', {})
                reject_reason = reject.get('reason', 'Message rejected by SES')

                success = tracker.track_bounce(
                    message_id=message_id,
                    bounce_type='hard',
                    bounce_reason=reject_reason
                )
                provider_stats['bounced'] = 1

            # Update provider reputation
            from ..core.provider_manager import ProviderManager
            provider_manager = ProviderManager(db_session=db)

            for event_name, count in provider_stats.items():
                for _ in range(count):
                    provider_manager.update_reputation('aws_ses', event_name)

            return {
                "success": True,
                "event_type": event_type,
                "message_id": message_id,
                "processed": success,
                "provider_stats": provider_stats,
                "raw_message": message  # Include for debugging
            }

        return {"message": "Unknown SNS message type", "type": payload.get('Type')}

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in SNS message: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing SES webhook: {str(e)}")

@webhook_router.post("/postmark")
async def postmark_webhook(request: Request, db=Depends(get_db_session)):
    """Handle Postmark webhook events with comprehensive processing"""

    # Get raw payload for signature verification
    payload = await request.body()

    # Verify signature (optional but recommended)
    signature = request.headers.get('X-Postmark-Signature')
    webhook_key = os.getenv('POSTMARK_WEBHOOK_KEY')

    if webhook_key and signature:
        if not verify_postmark_signature(payload, signature, webhook_key):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        event = json.loads(payload)
        tracker = EngagementTracker(db)

        record_type = event.get('RecordType')
        message_id = event.get('MessageID')
        email = event.get('Email')

        success = False
        provider_stats = {}

        if record_type == 'Delivery':
            delivered_at = event.get('DeliveredAt')
            success = tracker.track_delivery(message_id=message_id)
            provider_stats['delivered'] = 1

        elif record_type == 'Open':
            # Track open with detailed information
            client_info = event.get('Client', {})
            geo_info = event.get('Geo', {})

            success = tracker.track_open(
                message_id=message_id,
                user_agent=event.get('UserAgent'),
                ip_address=client_info.get('IP')
            )
            provider_stats['opened'] = 1

        elif record_type == 'Click':
            # Track click with link information
            success = tracker.track_click(
                message_id=message_id,
                clicked_url=event.get('OriginalLink'),
                user_agent=event.get('UserAgent'),
                ip_address=event.get('Client', {}).get('IP')
            )
            provider_stats['clicked'] = 1

        elif record_type == 'Bounce':
            # Map Postmark bounce types
            bounce_type_map = {
                'HardBounce': 'hard',
                'Transient': 'soft',
                'Unsubscribe': 'unsubscribe',
                'Subscribe': 'subscribe',
                'AutoResponder': 'auto_responder',
                'AddressChange': 'address_change',
                'DnsError': 'dns_error',
                'SpamNotification': 'spam',
                'OpenRelayTest': 'open_relay',
                'Unknown': 'unknown',
                'SoftBounce': 'soft',
                'VirusNotification': 'virus',
                'ChallengeVerification': 'challenge',
                'BadEmailAddress': 'hard',
                'SpamComplaint': 'spam',
                'ManuallyDeactivated': 'manual',
                'Unconfirmed': 'unconfirmed',
                'Blocked': 'blocked',
                'SMTPApiError': 'api_error',
                'InboundError': 'inbound_error',
                'DMARCPolicy': 'dmarc',
                'TemplateRenderingFailed': 'template_error'
            }

            postmark_type = event.get('Type', 'Unknown')
            bounce_type = bounce_type_map.get(postmark_type, 'hard')

            success = tracker.track_bounce(
                message_id=message_id,
                bounce_type=bounce_type,
                bounce_reason=f"{postmark_type}: {event.get('Description', '')}"
            )
            provider_stats['bounced'] = 1

        elif record_type == 'SpamComplaint':
            success = tracker.track_complaint(
                message_id=message_id,
                complaint_type='spam'
            )
            provider_stats['complained'] = 1

        elif record_type == 'SubscriptionChange':
            # Handle subscription changes
            suppress_sending = event.get('SuppressSending', False)
            if suppress_sending:
                success = tracker.track_unsubscribe(
                    message_id=message_id,
                    email=email
                )

        # Update provider reputation
        from ..core.provider_manager import ProviderManager
        provider_manager = ProviderManager(db_session=db)

        for event_name, count in provider_stats.items():
            for _ in range(count):
                provider_manager.update_reputation('postmark', event_name)

        return {
            "success": True,
            "record_type": record_type,
            "message_id": message_id,
            "email": email,
            "processed": success,
            "provider_stats": provider_stats,
            "event_details": {
                "timestamp": event.get('ReceivedAt'),
                "server_id": event.get('ServerID'),
                "tag": event.get('Tag')
            }
        }

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
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
