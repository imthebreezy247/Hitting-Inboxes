import pandas as pd
import time
import random
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Personalization, From, ReplyTo
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# SendGrid setup
sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))

# Load Excel file
df = pd.read_excel("subscribers.xlsx")

# Track results
results = {"sent": 0, "failed": 0, "emails": []}

def create_email(to_email, name):
    """Create email with anti-spam best practices"""
    
    # Personalized subject (helps avoid spam)
    subject = f"{name}, Congrats on Your USHA Contract - Referral Opportunity"
    
    # HTML content with personalization
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto;">
        <p>Hey there {name},</p>
        
        <p>Hope your year is going great so far and that you're crushing it at USHA!</p>
        
        <p>I'm <strong>Chris Shannahan</strong>, a licensed insurance agent with over five years of experience. 
        Since you're also working with USHA, I wanted to reach out about a partnership opportunity.</p>
        
        <p>As you know, USHA plans are underwritten, so not everyone gets approved. When that happens, 
        I can help you still earn from those leads:</p>
        
        <ul style="color: #2c5282;">
            <li><strong>$50</strong> for 1 person on 1 policy</li>
            <li><strong>$75</strong> for 2 people on 1 policy</li>
            <li><strong>$100</strong> for 3+ people on 1 policy</li>
        </ul>
        
        <p><strong>I pay immediately via Zelle or PayPal.</strong> Just text me the client info at 
        <a href="tel:9415180701">(941) 518-0701</a> and I'll handle everything.</p>
        
        <p>Looking forward to partnering with you!</p>
        
        <p>Best regards,<br>
        <strong>Chris Shannahan</strong><br>
        Licensed Insurance Agent<br>
        📱 (941) 518-0701<br>
        📧 chris@cjsinsurancesolutions.com</p>
        
        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
        
        <p style="font-size: 12px; color: #666; text-align: center;">
            This email was sent to {to_email} because you're a licensed insurance agent.<br>
            <a href="mailto:chris@cjsinsurancesolutions.com?subject=Unsubscribe&body=Please remove {to_email} from your list." 
               style="color: #0073e6;">Unsubscribe</a> | 
            <a href="https://cjsinsurancesolutions.com" style="color: #0073e6;">Visit Website</a>
        </p>
    </body>
    </html>
    """
    
    # Plain text version (IMPORTANT for spam prevention!)
    text_content = f"""
Hey there {name},

Hope your year is going great so far and that you're crushing it at USHA!

I'm Chris Shannahan, a licensed insurance agent with over five years of experience. 
Since you're also working with USHA, I wanted to reach out about a partnership opportunity.

When USHA plans don't get approved, I can help you still earn from those leads:
- $50 for 1 person on 1 policy
- $75 for 2 people on 1 policy
- $100 for 3+ people on 1 policy

I pay immediately via Zelle or PayPal. Just text me at (941) 518-0701.

Looking forward to partnering with you!

Best regards,
Chris Shannahan
Licensed Insurance Agent
(941) 518-0701
chris@cjsinsurancesolutions.com

To unsubscribe, reply with "UNSUBSCRIBE" in the subject line.
    """
    
    # Create message with best practices
    message = Mail()
    
    # From email with name (builds trust)
    message.from_email = From('chris@cjsinsurancesolutions.com', 'Chris Shannahan')
    
    # Reply-to (shows legitimacy)
    message.reply_to = ReplyTo('chris@cjsinsurancesolutions.com', 'Chris Shannahan')
    
    # Personalization
    personalization = Personalization()
    personalization.add_to((to_email, name))
    personalization.subject = subject
    message.add_personalization(personalization)
    
    # Both HTML and plain text (critical for deliverability!)
    message.add_content(text_content, 'text/plain')
    message.add_content(html_content, 'text/html')
    
    # Custom headers for better deliverability
    message.add_header('X-Priority', '3')  # Normal priority
    message.add_header('List-Unsubscribe', '<mailto:chris@cjsinsurancesolutions.com?subject=Unsubscribe>')
    
    return message

def send_email(email, name, index, total):
    """Send email with SendGrid"""
    try:
        message = create_email(email, name)
        response = sg.send(message)
        
        print(f"✅ [{index+1}/{total}] Sent to {name} ({email}) - Status: {response.status_code}")
        results["sent"] += 1
        results["emails"].append({"email": email, "status": "sent", "time": datetime.now()})
        return True
        
    except Exception as e:
        print(f"❌ [{index+1}/{total}] Failed: {email} - Error: {str(e)}")
        results["failed"] += 1
        results["emails"].append({"email": email, "status": "failed", "error": str(e)})
        return False

# MAIN SENDING LOOP
print(f"📧 Starting to send {len(df)} emails via SendGrid...")
print(f"⏰ Estimated time: {len(df) * 8} minutes\n")

for index, row in df.iterrows():
    email = row["Email"]
    name = row["Name"]
    
    # Send email
    send_email(email, name, index, len(df))
    
    # Smart delay (except for last email)
    if index < len(df) - 1:
        # Your original delay: 7-10 minutes
        delay = 420 + random.randint(60, 180)
        
        # Show progress
        next_send = datetime.now().strftime("%I:%M %p")
        print(f"⏳ Waiting {delay//60} minutes... Next email at ~{next_send}\n")
        
        time.sleep(delay)

# Final report
print("\n" + "="*50)
print("📊 FINAL REPORT")
print("="*50)
print(f"✅ Successfully sent: {results['sent']}")
print(f"❌ Failed: {results['failed']}")
print(f"📧 Total processed: {len(df)}")
print(f"🎯 Success rate: {(results['sent']/len(df)*100):.1f}%")

# Save results
results_df = pd.DataFrame(results["emails"])
results_df.to_csv(f"send_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", index=False)
print(f"\n💾 Results saved to: send_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")