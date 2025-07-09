# app.py
from flask import Flask, request, jsonify
from email_sender import EmailDeliverySystem
from list_manager import SubscriberManager
from templates import get_email_template
from utils.dns_checker import DNSChecker
from database.models import db
import os
from datetime import datetime

app = Flask(__name__)
email_system = EmailDeliverySystem()
subscriber_manager = SubscriberManager()
dns_checker = DNSChecker()

@app.route('/send-campaign', methods=['POST'])
def send_campaign():
    """Send email campaign to all active subscribers"""
    data = request.json
    subject = data.get('subject')
    content = data.get('content')
    segment = data.get('segment', 'general')

    # Create campaign record
    campaign_id = db.execute_update('''
        INSERT INTO campaigns (name, subject, status, total_recipients)
        VALUES (?, ?, 'sending', 0)
    ''', (f"Campaign: {subject}", subject))

    # Get subscribers based on segment
    if segment == 'all':
        active_subscribers = subscriber_manager.clean_list()
    elif segment == 'high_engagement':
        active_subscribers = subscriber_manager.get_high_engagement_subscribers()
    else:
        active_subscribers = subscriber_manager.get_subscribers_by_segment(segment)

    if not active_subscribers:
        return jsonify({
            'error': 'No active subscribers found for the specified segment',
            'segment': segment
        }), 400

    # Get email templates
    html_template, text_template = get_email_template()

    # Prepare campaign data
    campaign_data = []
    for sub in active_subscribers:
        subscriber_data = {
            'email': sub['email'],
            'name': sub['name'],
            'content': content,
            'campaign_id': campaign_id,
            'subscriber_id': sub.get('id'),
            'unsubscribe_link': f"https://cjsinsurancesolutions.com/unsubscribe?email={sub['email']}",
            'preferences_link': f"https://cjsinsurancesolutions.com/preferences?email={sub['email']}"
        }
        campaign_data.append(subscriber_data)

    # Update campaign with total recipients
    db.execute_update('''
        UPDATE campaigns SET total_recipients = ? WHERE id = ?
    ''', (len(campaign_data), campaign_id))

    # Send emails using multi-ESP system
    sent_count, failed_emails = email_system.send_batch_emails(
        campaign_data,
        subject,
        html_template,
        text_template,
        campaign_id
    )

    return jsonify({
        'campaign_id': campaign_id,
        'sent': sent_count,
        'failed': len(failed_emails),
        'failed_emails': failed_emails,
        'segment': segment,
        'esp_status': email_system.get_esp_status()
    })

@app.route('/add-subscriber', methods=['POST'])
def add_subscriber():
    """Add new subscriber"""
    data = request.json
    success = subscriber_manager.add_subscriber(
        data['email'],
        data['name'],
        data.get('company'),
        data.get('source', 'api'),
        data.get('segment', 'general')
    )

    if success:
        return jsonify({'status': 'success', 'message': 'Subscriber added successfully'})
    else:
        return jsonify({'status': 'error', 'message': 'Invalid email address'}), 400

@app.route('/unsubscribe', methods=['GET'])
def unsubscribe():
    """Handle unsubscribe requests"""
    email = request.args.get('email')
    success = subscriber_manager.unsubscribe(email)

    if success:
        return "You have been successfully unsubscribed."
    else:
        return "Error processing unsubscribe request.", 500

@app.route('/dns-check', methods=['GET'])
def dns_check():
    """Check DNS configuration status"""
    results = dns_checker.run_full_dns_check()
    return jsonify(results)

@app.route('/dns-instructions', methods=['GET'])
def dns_instructions():
    """Get DNS setup instructions"""
    instructions = dns_checker.generate_dns_setup_instructions()
    return jsonify({'instructions': instructions})

@app.route('/esp-status', methods=['GET'])
def esp_status():
    """Get ESP performance status"""
    status = email_system.get_esp_status()
    return jsonify(status)

@app.route('/subscriber-stats', methods=['GET'])
def subscriber_stats():
    """Get subscriber statistics"""
    stats = subscriber_manager.get_subscriber_stats()
    return jsonify(stats)

@app.route('/bounce-webhook', methods=['POST'])
def bounce_webhook():
    """Handle bounce webhooks from ESPs"""
    data = request.json

    # Determine ESP from headers or data
    esp_provider = request.headers.get('X-ESP-Provider', 'unknown')

    # Process bounce based on ESP format
    if 'email' in data and 'bounce_type' in data:
        subscriber_manager.record_bounce(
            data['email'],
            data['bounce_type'],
            data.get('bounce_reason'),
            esp_provider,
            data.get('campaign_id')
        )

    return jsonify({'status': 'processed'})

@app.route('/complaint-webhook', methods=['POST'])
def complaint_webhook():
    """Handle complaint webhooks from ESPs"""
    data = request.json

    esp_provider = request.headers.get('X-ESP-Provider', 'unknown')

    if 'email' in data:
        subscriber_manager.record_complaint(
            data['email'],
            data.get('complaint_type', 'spam'),
            esp_provider,
            data.get('campaign_id')
        )

    return jsonify({'status': 'processed'})

@app.route('/engagement-webhook', methods=['POST'])
def engagement_webhook():
    """Handle engagement webhooks (opens, clicks)"""
    data = request.json

    if 'email' in data and 'event_type' in data:
        subscriber_manager.update_engagement(
            data['email'],
            data['event_type']
        )

    return jsonify({'status': 'processed'})

if __name__ == '__main__':
    app.run(debug=True)