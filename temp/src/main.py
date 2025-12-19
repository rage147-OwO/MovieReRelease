"""
AiMate FastAPI application entry point.
Instagram story auto-responder with AI-powered analysis and reaction generation.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.api.webhook import router as webhook_router
from src.utils.logger import logger
from src.utils.env import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("🚀 Starting AiMate Instagram Auto-Responder")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Target accounts: {len(settings.target_accounts_list)}")
    
    # Validate critical configuration
    startup_checks = {
        "Instagram credentials": bool(settings.instagram_username and settings.instagram_password),
        "OpenAI API key": bool(settings.openai_api_key),
        "Target accounts": bool(settings.target_accounts_list)
    }
    
    for check_name, check_result in startup_checks.items():
        status = "✓" if check_result else "✗"
        logger.info(f"{status} {check_name}: {'Configured' if check_result else 'Missing'}")
    
    missing_configs = [name for name, result in startup_checks.items() if not result]
    if missing_configs:
        logger.warning(f"Missing configuration: {', '.join(missing_configs)}")
        logger.warning("Some features may not work properly. Check your .env file.")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down AiMate")


# Create FastAPI application
app = FastAPI(
    title="AiMate - Instagram Auto-Responder",
    description="AI-powered Instagram story auto-responder using OpenAI Vision API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else ["https://localhost"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhook_router, prefix="/api/v1", tags=["webhooks"])


@app.get("/")
async def root():
    """Root endpoint with basic app information."""
    return {
        "name": "AiMate",
        "description": "Instagram Story Auto-Responder",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/api/v1/health",
            "trigger": "/api/v1/trigger",
            "accounts": "/api/v1/accounts",
            "config": "/api/v1/config",
            "docs": "/docs"
        }
    }


@app.get("/status")
async def status():
    """Quick status check."""
    return {
        "status": "running",
        "environment": settings.environment,
        "configured_accounts": len(settings.target_accounts_list)
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    if settings.environment == "development":
        # In development, show detailed error
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": str(exc),
                "type": type(exc).__name__
            }
        )
    else:
        # In production, show generic error
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": "An unexpected error occurred"
            }
        )


# HTTP exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions with logging."""
    logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


# Health check for load balancers
@app.get("/ping")
async def ping():
    """Simple ping endpoint for load balancers."""
    return {"ping": "pong"}


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting AiMate server on {settings.host}:{settings.port}")
    
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
        access_log=True
    )
