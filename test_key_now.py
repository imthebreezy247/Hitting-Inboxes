import os
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient

# Load your .env file
load_dotenv()

api_key = os.getenv('SENDGRID_API_KEY')
print(f"Testing API key: {api_key[:15]}...")

try:
    sg = SendGridAPIClient(api_key)
    
    # Simple test - get user profile
    response = sg.client.user.profile.get()
    print("✅ API Key is VALID and working!")
    
except Exception as e:
    error_msg = str(e)
    if "401" in error_msg:
        print("❌ API Key is INVALID or has wrong permissions")
        print("Fix: Create a new API key with 'Full Access' in SendGrid")
    elif "verified Sender Identity" in error_msg:
        print("❌ You need to verify your email address first!")
        print("Fix: Go to SendGrid → Sender Authentication → Verify Single Sender")
    else:
        print(f"❌ Error: {error_msg}")