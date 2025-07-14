import pandas as pd
import time
import random
import os
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

# Force reload environment variables
load_dotenv(override=True)

# Configuration
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
EXCEL_FILE = r"C:\Scripts\subscribers1.xlsx"
TEST_MODE = True  # Set to False to send to everyone
TEST_LIMIT = 3    # How many to send in test mode

print("="*60)
print("📧 EMAIL SENDER - SENDGRID VERSION")
print("="*60)

# Verify API key
if not SENDGRID_API_KEY:
    print("❌ No API key found!")
    exit()
else:
    print(f"✅ API Key loaded: {SENDGRID_API_KEY[:20]}...")

# Initialize SendGrid
sg = SendGridAPIClient(SENDGRID_API_KEY)

# Load Excel
try:
    df = pd.read_excel(EXCEL_FILE)
    print(f"✅ Loaded {len(df)} contacts")
    print("\nFirst few contacts:")
    print(df.head())
except Exception as e:
    print(f"❌ Error loading Excel: {e}")
    exit()

# Confirm before sending
print(f"\n⚠️  TEST MODE: {'ON' if TEST_MODE else 'OFF'}")
print(f"Will send to: {TEST_LIMIT if TEST_MODE else len(df)} contacts")

if input("\n👉 Ready to send? (yes/no): ").lower() != 'yes':
    print("Cancelled!")
    exit()

# Email template
def create_email(to_email, name):
    return Mail(
        from_email='chris@cjsinsurancesolutions.com',
        to_emails=to_email,
        subject=f'{name}, Partnership Opportunity with CJS Insurance',
        html_content=f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
            <p>Hey there {name},</p>
            
            <p>Hope you're crushing it at USHA!</p>
            
            <p>I'm Chris Shannahan, a fellow insurance agent. When your USHA clients 
            don't get approved, I can help you still earn:</p>
            
            <ul>
                <li><strong>$50</strong> for 1 person</li>
                <li><strong>$75</strong> for 2 people</li>
                <li><strong>$100</strong> for 3+ people</li>
            </ul>
            
            <p>I pay immediately via Zelle/PayPal!</p>
            
            <p>Text me: <strong>(941) 518-0701</strong></p>
            
            <p>Best,<br>Chris Shannahan</p>
        </body>
        </html>
        """
    )

# Send emails
sent = 0
failed = 0
emails_to_send = df.head(TEST_LIMIT) if TEST_MODE else df

print(f"\n🚀 Sending emails...\n")

for index, row in emails_to_send.iterrows():
    email = row['Email']
    name = row['Name']
    
    try:
        message = create_email(email, name)
        response = sg.send(message)
        sent += 1
        print(f"✅ [{sent}/{len(emails_to_send)}] Sent to {name} ({email})")
        
    except Exception as e:
        failed += 1
        print(f"❌ Failed to {name}: {str(e)}")
    
    # Wait between emails
    if index < len(emails_to_send) - 1:
        wait = random.randint(5, 10)
        print(f"⏳ Waiting {wait} seconds...")
        time.sleep(wait)

# Results
print("\n" + "="*60)
print(f"📊 COMPLETE!")
print(f"✅ Sent: {sent}")
print(f"❌ Failed: {failed}")
print("="*60)

# Check your email!
if sent > 0:
    print("\n📬 Check the inbox for the test emails!")