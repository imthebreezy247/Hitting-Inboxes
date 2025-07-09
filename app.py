# app.py
from flask import Flask, request, jsonify
from email_sender import EmailDeliverySystem
from list_manager import SubscriberManager
from templates import get_email_template
import os

app = Flask(__name__)
email_system = EmailDeliverySystem()
subscriber_manager = SubscriberManager()

@app.route('/send-campaign', methods=['POST'])
def send_campaign():
    """Send email campaign to all active subscribers"""
    data = request.json
    subject = data.get('subject')
    content = data.get('content')
    
    # Get active subscribers
    active_subscribers = subscriber_manager.clean_list()
    
    # Get email templates
    html_template, text_template = get_email_template()
    
    # Prepare campaign data
    campaign_data = []
    for sub in active_subscribers:
        subscriber_data = {
            'email': sub['email'],
            'name': sub['name'],
            'content': content,
            'unsubscribe_link': f"https://cjsinsurancesolutions.com/unsubscribe?email={sub['email']}",
            'preferences_link': f"https://cjsinsurancesolutions.com/preferences?email={sub['email']}"
        }
        campaign_data.append(subscriber_data)
    
    # Send emails
    sent_count, failed_emails = email_system.send_batch_emails(
        campaign_data, 
        subject, 
        html_template, 
        text_template
    )
    
    return jsonify({
        'sent': sent_count,
        'failed': len(failed_emails),
        'failed_emails': failed_emails
    })

@app.route('/add-subscriber', methods=['POST'])
def add_subscriber():
    """Add new subscriber"""
    data = request.json
    subscriber_manager.add_subscriber(
        data['email'],
        data['name'],
        data.get('company')
    )
    return jsonify({'status': 'success'})

@app.route('/unsubscribe', methods=['GET'])
def unsubscribe():
    """Handle unsubscribe requests"""
    email = request.args.get('email')
    subscriber_manager.unsubscribe(email)
    return "You have been successfully unsubscribed."

if __name__ == '__main__':
    app.run(debug=True)