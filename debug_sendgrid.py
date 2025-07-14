import os
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Reload environment variables
load_dotenv(override=True)

api_key = os.getenv('SENDGRID_API_KEY')
print(f"1. API Key loaded: {'YES' if api_key else 'NO'}")
print(f"   Key preview: {api_key[:20]}..." if api_key else "   No key found!")

try:
    # Initialize SendGrid
    sg = SendGridAPIClient(api_key)
    print("2. SendGrid client created: YES")
    
    # Create a simple test message
    message = Mail(
        from_email='chris@cjsinsurancesolutions.com',
        to_emails='cshannahan247@gmail.com',
        subject='SendGrid Test - Debug',
        html_content='<p>This is a test email to debug SendGrid.</p>'
    )
    print("3. Email message created: YES")
    
    # Try to send
    print("4. Attempting to send...")
    response = sg.send(message)
    
    print(f"✅ SUCCESS! Email sent!")
    print(f"   Status Code: {response.status_code}")
    print(f"   Message ID: {response.headers.get('X-Message-Id', 'N/A')}")
    
except Exception as e:
    print(f"\n❌ ERROR: {type(e).__name__}")
    print(f"   Message: {str(e)}")
    
    # Get more details if available
    if hasattr(e, 'status_code'):
        print(f"   Status Code: {e.status_code}")
    if hasattr(e, 'body'):
        print(f"   Body: {e.body}")
    if hasattr(e, 'headers'):
        print(f"   Headers: {dict(e.headers)}")

print("\n5. Checking environment:")
print(f"   .env file exists: {os.path.exists('.env')}")
print(f"   Current directory: {os.getcwd()}")