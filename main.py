# main.py - FastAPI Application Entry Point
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routes
from src.api.routes import app as routes_app
from src.api.webhooks import webhook_router

# Create main FastAPI application
app = FastAPI(
    title="Email Delivery System",
    description="High-deliverability email system with multi-ESP support, IP warming, and advanced analytics",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include routers
app.mount("/api", routes_app)
app.include_router(webhook_router)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Email Delivery System",
        "version": "2.0.0"
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with system information"""
    return {
        "message": "Email Delivery System API v2.0",
        "status": "operational",
        "documentation": "/docs",
        "health": "/health",
        "features": [
            "Multi-ESP support (SendGrid, Amazon SES, Postmark)",
            "Intelligent provider selection and failover",
            "IP warming automation with performance monitoring",
            "Advanced engagement tracking and analytics",
            "Subscriber management with segmentation",
            "Real-time webhook processing",
            "Campaign performance optimization",
            "Deliverability monitoring and alerts"
        ],
        "endpoints": {
            "api": "/api",
            "webhooks": "/webhooks",
            "documentation": "/docs",
            "health": "/health"
        }
    }

if __name__ == "__main__":
    # Configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    # Run the application
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if not debug else "debug"
    )
