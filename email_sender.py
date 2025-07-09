# email_sender.py
import os
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from email_validator import validate_email, EmailNotValidError
import pandas as pd
from datetime import datetime
import time
from dotenv import load_dotenv

load_dotenv()

class EmailDeliverySystem:
    def __init__(self):
        self.sg = sendgrid.SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))
        self.from_email = os.environ.get('FROM_EMAIL')
        self.daily_limit = 3000
        self.batch_size = 100
        self.delay_between_batches = 5  # seconds
        
    def validate_email_list(self, email_list):
        """Validate and clean email list"""
        valid_emails = []
        invalid_emails = []
        
        for email in email_list:
            try:
                validated = validate_email(email)
                valid_emails.append(validated.email)
            except EmailNotValidError:
                invalid_emails.append(email)
                
        return valid_emails, invalid_emails
    
    def create_personalized_content(self, template, subscriber_data):
        """Personalize email content for each subscriber"""
        content = template
        for key, value in subscriber_data.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(value))
        return content
    
    def send_batch_emails(self, subscribers, subject, html_template, text_template):
        """Send emails in batches with rate limiting"""
        sent_count = 0
        failed_emails = []
        
        # Process in batches
        for i in range(0, len(subscribers), self.batch_size):
            batch = subscribers[i:i + self.batch_size]
            
            for subscriber in batch:
                try:
                    # Personalize content
                    html_content = self.create_personalized_content(
                        html_template, 
                        subscriber
                    )
                    text_content = self.create_personalized_content(
                        text_template, 
                        subscriber
                    )
                    
                    # Create message
                    message = Mail(
                        from_email=Email(self.from_email, "CJS Insurance Solutions"),
                        to_emails=To(subscriber['email']),
                        subject=subject,
                        html_content=Content("text/html", html_content),
                        plain_text_content=Content("text/plain", text_content)
                    )
                    
                    # Add headers for better deliverability
                    message.reply_to = Email(self.from_email)
                    message.add_header('List-Unsubscribe', f'<mailto:unsubscribe@cjsinsurancesolutions.com?subject=Unsubscribe>')
                    
                    # Send email
                    response = self.sg.send(message)
                    
                    if response.status_code == 202:
                        sent_count += 1
                        print(f"Sent to {subscriber['email']}")
                    else:
                        failed_emails.append(subscriber['email'])
                        
                except Exception as e:
                    print(f"Failed to send to {subscriber['email']}: {str(e)}")
                    failed_emails.append(subscriber['email'])
                    
                # Rate limiting
                if sent_count >= self.daily_limit:
                    print(f"Daily limit of {self.daily_limit} reached")
                    break
                    
            # Delay between batches
            if i + self.batch_size < len(subscribers):
                time.sleep(self.delay_between_batches)
                
        return sent_count, failed_emails