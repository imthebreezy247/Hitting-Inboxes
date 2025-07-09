#!/bin/bash

# deploy.sh - Production deployment script for Email Delivery System Phase 2
# This script sets up the complete production environment

set -e  # Exit on any error

echo "======================================="
echo "Email Delivery System - Phase 2 Deployment"
echo "======================================="

# Configuration
PROJECT_NAME="email-delivery-system"
PROJECT_DIR="/opt/$PROJECT_NAME"
SERVICE_USER="emailsys"
PYTHON_VERSION="3.9"
DB_NAME="email_delivery_system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   error "This script should not be run as root for security reasons"
fi

# Check system requirements
check_requirements() {
    log "Checking system requirements..."
    
    # Check Python version
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is not installed"
    fi
    
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    log "Python version: $python_version"
    
    # Check PostgreSQL
    if ! command -v psql &> /dev/null; then
        error "PostgreSQL is not installed. Please install PostgreSQL first."
    fi
    
    # Check Redis
    if ! command -v redis-cli &> /dev/null; then
        warn "Redis is not installed. Installing Redis..."
        sudo apt-get update
        sudo apt-get install -y redis-server
    fi
    
    # Check Git
    if ! command -v git &> /dev/null; then
        error "Git is not installed"
    fi
    
    log "System requirements check completed"
}

# Create project directory and user
setup_project_structure() {
    log "Setting up project structure..."
    
    # Create project directory
    sudo mkdir -p $PROJECT_DIR
    sudo chown $USER:$USER $PROJECT_DIR
    
    # Copy project files
    if [ -d "src" ]; then
        cp -r . $PROJECT_DIR/
        cd $PROJECT_DIR
    else
        error "Source files not found. Please run this script from the project root directory."
    fi
    
    log "Project structure created at $PROJECT_DIR"
}

# Set up Python virtual environment
setup_python_environment() {
    log "Setting up Python virtual environment..."
    
    cd $PROJECT_DIR
    
    # Create virtual environment
    python3 -m venv venv
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install dependencies
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        log "Dependencies installed successfully"
    else
        error "requirements.txt not found"
    fi
    
    # Install additional production dependencies
    pip install gunicorn supervisor psycopg2-binary
    
    log "Python environment setup completed"
}

# Set up PostgreSQL database
setup_database() {
    log "Setting up PostgreSQL database..."
    
    # Create database user
    sudo -u postgres createuser --interactive --pwprompt $SERVICE_USER || warn "User may already exist"
    
    # Create database
    sudo -u postgres createdb -O $SERVICE_USER $DB_NAME || warn "Database may already exist"
    
    # Grant privileges
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $SERVICE_USER;"
    
    log "Database setup completed"
}

# Configure environment variables
setup_environment() {
    log "Setting up environment configuration..."
    
    cd $PROJECT_DIR
    
    # Create .env file if it doesn't exist
    if [ ! -f ".env" ]; then
        cat > .env << EOL
# Database Configuration
DATABASE_URL=postgresql://$SERVICE_USER:password@localhost/$DB_NAME

# Application Configuration
SECRET_KEY=$(openssl rand -hex 32)
ENVIRONMENT=production
DEBUG=false
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Email Provider API Keys (UPDATE THESE)
SENDGRID_API_KEY=your_sendgrid_api_key_here
SENDGRID_WEBHOOK_KEY=your_sendgrid_webhook_key_here

AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here
AWS_REGION=us-east-1

POSTMARK_SERVER_TOKEN=your_postmark_server_token_here
POSTMARK_API_KEY=your_postmark_api_key_here
POSTMARK_WEBHOOK_KEY=your_postmark_webhook_key_here

# Domain Configuration
FROM_EMAIL=chris@mail.cjsinsurancesolutions.com
FROM_NAME=Chris - CJS Insurance Solutions
DOMAIN=cjsinsurancesolutions.com

# Monitoring
SENTRY_DSN=your_sentry_dsn_here
EOL
        
        log "Environment file created. Please update API keys in .env"
    else
        log "Environment file already exists"
    fi
    
    # Set proper permissions
    chmod 600 .env
}

# Initialize database schema
initialize_database() {
    log "Initializing database schema..."
    
    cd $PROJECT_DIR
    source venv/bin/activate
    
    # Run database migrations
    python -c "
from src.database.models import create_tables
create_tables()
print('Database tables created successfully')
"
    
    log "Database schema initialized"
}

# Create systemd service
setup_systemd_service() {
    log "Setting up systemd service..."
    
    sudo tee /etc/systemd/system/email-delivery.service > /dev/null << EOL
[Unit]
Description=Email Delivery System
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$PROJECT_DIR

[Install]
WantedBy=multi-user.target
EOL
    
    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable email-delivery.service
    
    log "Systemd service created and enabled"
}

# Set up monitoring
setup_monitoring() {
    log "Setting up monitoring..."
    
    cd $PROJECT_DIR
    
    # Create monitoring script
    cat > monitor.py << 'EOL'
#!/usr/bin/env python3
"""
System monitoring script for Email Delivery System
"""
import requests
import time
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitoring.log'),
        logging.StreamHandler()
    ]
)

def check_health():
    """Check system health"""
    try:
        response = requests.get("http://localhost:8000/system/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            health_score = data.get('health_score', 0)
            status = data.get('status', 'unknown')
            
            logging.info(f"System {status} - Health Score: {health_score:.1f}")
            
            # Check for alerts
            if health_score < 80:
                logging.warning(f"Low health score: {health_score:.1f}")
            
            if status == 'unhealthy':
                logging.error("System is unhealthy!")
                
        else:
            logging.error(f"Health check failed - Status: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Health check failed - Error: {e}")

def check_alerts():
    """Check system alerts"""
    try:
        response = requests.get("http://localhost:8000/system/alerts", timeout=10)
        if response.status_code == 200:
            data = response.json()
            alerts = data.get('alerts', [])
            warnings = data.get('warnings', [])
            
            for alert in alerts:
                logging.error(f"ALERT: {alert['message']}")
            
            for warning in warnings:
                logging.warning(f"WARNING: {warning['message']}")
                
    except requests.exceptions.RequestException as e:
        logging.error(f"Alert check failed - Error: {e}")

def main():
    """Main monitoring loop"""
    logging.info("Starting Email Delivery System monitoring...")
    
    while True:
        try:
            check_health()
            check_alerts()
            time.sleep(300)  # Check every 5 minutes
        except KeyboardInterrupt:
            logging.info("Monitoring stopped by user")
            break
        except Exception as e:
            logging.error(f"Monitoring error: {e}")
            time.sleep(60)  # Wait 1 minute before retrying

if __name__ == "__main__":
    main()
EOL
    
    chmod +x monitor.py
    
    # Create monitoring service
    sudo tee /etc/systemd/system/email-delivery-monitor.service > /dev/null << EOL
[Unit]
Description=Email Delivery System Monitor
After=email-delivery.service
Wants=email-delivery.service

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/monitor.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOL
    
    sudo systemctl daemon-reload
    sudo systemctl enable email-delivery-monitor.service
    
    log "Monitoring setup completed"
}

# Set up log rotation
setup_log_rotation() {
    log "Setting up log rotation..."
    
    sudo tee /etc/logrotate.d/email-delivery > /dev/null << EOL
$PROJECT_DIR/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $USER $USER
    postrotate
        systemctl reload email-delivery.service
    endscript
}
EOL
    
    log "Log rotation configured"
}

# Run health checks
run_health_checks() {
    log "Running health checks..."
    
    cd $PROJECT_DIR
    source venv/bin/activate
    
    # Test database connection
    python -c "
from src.database.models import get_db
try:
    db = next(get_db())
    db.execute('SELECT 1')
    print('✓ Database connection successful')
except Exception as e:
    print(f'✗ Database connection failed: {e}')
    exit(1)
"
    
    # Test API startup
    timeout 30 python -c "
import uvicorn
from main import app
print('✓ API startup test successful')
" || error "API startup test failed"
    
    log "Health checks completed successfully"
}

# Main deployment function
main() {
    log "Starting Email Delivery System deployment..."
    
    check_requirements
    setup_project_structure
    setup_python_environment
    setup_database
    setup_environment
    initialize_database
    setup_systemd_service
    setup_monitoring
    setup_log_rotation
    run_health_checks
    
    log "Deployment completed successfully!"
    echo ""
    echo "======================================="
    echo "DEPLOYMENT SUMMARY"
    echo "======================================="
    echo "Project Directory: $PROJECT_DIR"
    echo "Database: $DB_NAME"
    echo "Service: email-delivery.service"
    echo "Monitor: email-delivery-monitor.service"
    echo ""
    echo "NEXT STEPS:"
    echo "1. Update API keys in $PROJECT_DIR/.env"
    echo "2. Configure DNS records for your domain"
    echo "3. Start services: sudo systemctl start email-delivery"
    echo "4. Check status: sudo systemctl status email-delivery"
    echo "5. View logs: journalctl -u email-delivery -f"
    echo "6. Access API: http://localhost:8000/docs"
    echo ""
    echo "IMPORTANT: Update the API keys in .env before starting the service!"
    echo "======================================="
}

# Run main function
main "$@"
