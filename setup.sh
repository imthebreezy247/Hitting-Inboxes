#!/bin/bash

# Email Delivery System Setup Script - Phase 1
echo "=== Email Delivery System Setup - Phase 1 ==="
echo ""

# Check Python version
python_version=$(python3 --version 2>&1)
echo "Python version: $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cat > .env << EOL
# SendGrid Configuration
SENDGRID_API_KEY=your_sendgrid_api_key_here
SENDGRID_FROM_EMAIL=chris@mail.cjsinsurancesolutions.com
SENDGRID_DAILY_LIMIT=1500
SENDGRID_HOURLY_LIMIT=100
SENDGRID_BATCH_SIZE=50
SENDGRID_DELAY=2.0

# Amazon SES Configuration
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here
AWS_REGION=us-east-1
SES_FROM_EMAIL=chris@mail.cjsinsurancesolutions.com
SES_DAILY_LIMIT=1000
SES_HOURLY_LIMIT=80
SES_BATCH_SIZE=40
SES_DELAY=3.0

# Postmark Configuration
POSTMARK_API_KEY=your_postmark_api_key_here
POSTMARK_SERVER_TOKEN=your_postmark_server_token_here
POSTMARK_FROM_EMAIL=chris@mail.cjsinsurancesolutions.com
POSTMARK_DAILY_LIMIT=500
POSTMARK_HOURLY_LIMIT=50
POSTMARK_BATCH_SIZE=25
POSTMARK_DELAY=4.0

# General Configuration
FROM_NAME=Chris - CJS Insurance Solutions
FROM_EMAIL=chris@mail.cjsinsurancesolutions.com
EOL
    echo "Created .env file with default values. Please update with your actual API keys."
else
    echo ".env file already exists."
fi

# Initialize database
echo "Initializing database..."
python3 -c "
from database.models import db
print('Database initialized successfully!')

# Migrate existing JSON data if present
if db.migrate_from_json():
    print('Migrated existing subscriber data from JSON to database.')
"

# Run DNS check
echo ""
echo "Running DNS configuration check..."
python3 -c "
from utils.dns_checker import DNSChecker
dns_checker = DNSChecker()
results = dns_checker.run_full_dns_check()

if results:
    print(f'DNS Check Results for {results.get(\"domain\", \"unknown\")}:')
    print(f'Overall Score: {results.get(\"overall_score\", 0):.1f}%')
    print(f'Valid Checks: {results.get(\"valid_checks\", 0)}/{results.get(\"total_checks\", 0)}')
    print('')
    print('DNS Setup Instructions:')
    print(dns_checker.generate_dns_setup_instructions())
else:
    print('Could not load domain configuration. Please check config/domain_setup.json')
"

echo ""
echo "=== Phase 1 Setup Complete ==="
echo ""
echo "Next Steps:"
echo "1. Update .env file with your actual API keys"
echo "2. Configure DNS records as shown above"
echo "3. Verify ESP accounts and domain authentication"
echo "4. Test the system with: python3 app.py"
echo ""
echo "API Endpoints available:"
echo "- POST /send-campaign - Send email campaign"
echo "- POST /add-subscriber - Add new subscriber"
echo "- GET /unsubscribe - Unsubscribe endpoint"
echo "- GET /dns-check - Check DNS configuration"
echo "- GET /esp-status - Check ESP status"
echo "- GET /subscriber-stats - Get subscriber statistics"
echo ""
echo "Ready for Phase 2 implementation!"