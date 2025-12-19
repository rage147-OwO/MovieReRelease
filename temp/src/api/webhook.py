"""
FastAPI webhook endpoints for AiMate Instagram auto-responder.
Provides health check and manual trigger endpoints.
"""

import asyncio
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from src.services.scraper import InstagramScraper
from src.services.analyzer import StoryAnalyzer
from src.services.reply_generator import ReplyGenerator
from src.services.dm_sender import DMSender
from src.utils.env import settings
from src.utils.logger import logger


# Request/Response models
class TriggerRequest(BaseModel):
    """Request model for manual trigger endpoint."""
    accounts: Optional[List[str]] = None
    send_messages: bool = False  # Whether to actually send DMs
    analysis_only: bool = False  # Just analyze, don't generate reactions


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str = "1.0.0"
    services: Dict[str, str]


class TriggerResponse(BaseModel):
    """Response model for trigger endpoint."""
    success: bool
    message: str
    results: Dict[str, Any]


class StoryProcessingResult(BaseModel):
    """Result of processing stories for one user."""
    username: str
    stories_found: int
    stories_analyzed: int
    reactions_generated: int
    messages_sent: int
    errors: List[str]


# Create router
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint to verify service status.
    Returns status of all major components.
    """
    logger.info("Health check requested")
    
    services_status = {
        "scraper": "unknown",
        "analyzer": "unknown", 
        "reply_generator": "unknown",
        "dm_sender": "unknown",
        "openai": "unknown"
    }
    
    try:
        # Test OpenAI connection
        from config.openai_config import openai_config
        openai_healthy = await openai_config.test_connection()
        services_status["openai"] = "healthy" if openai_healthy else "unhealthy"
        
        # Other services are harder to test without credentials
        # For now, mark them as available if modules load
        services_status["scraper"] = "available"
        services_status["analyzer"] = "available"
        services_status["reply_generator"] = "available"
        services_status["dm_sender"] = "available"
        
        overall_status = "healthy" if openai_healthy else "degraded"
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        overall_status = "unhealthy"
        services_status["openai"] = f"error: {str(e)}"
    
    return HealthResponse(
        status=overall_status,
        services=services_status
    )


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_story_processing(request: TriggerRequest, background_tasks: BackgroundTasks):
    """
    Manually trigger story analysis and reaction generation.
    
    This endpoint will:
    1. Scrape stories from specified accounts (or all target accounts)
    2. Analyze story content using AI
    3. Generate natural reactions
    4. Optionally send DMs with reactions
    """
    logger.info(f"Manual trigger requested: {request}")
    
    try:
        # Determine which accounts to process
        target_accounts = request.accounts or settings.target_accounts_list
        
        if not target_accounts:
            raise HTTPException(
                status_code=400,
                detail="No target accounts specified. Set TARGET_ACCOUNTS in environment or provide accounts in request."
            )
        
        # Validate Instagram credentials
        if not settings.instagram_username or not settings.instagram_password:
            raise HTTPException(
                status_code=400,
                detail="Instagram credentials not configured. Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD."
            )
        
        if request.analysis_only:
            # Run analysis in background
            background_tasks.add_task(
                _process_stories_analysis_only,
                target_accounts
            )
            return TriggerResponse(
                success=True,
                message=f"Started analysis-only processing for {len(target_accounts)} accounts",
                results={"accounts": target_accounts, "mode": "analysis_only"}
            )
        
        elif request.send_messages:
            # Run full processing with message sending in background
            background_tasks.add_task(
                _process_stories_with_sending,
                target_accounts
            )
            return TriggerResponse(
                success=True,
                message=f"Started full processing with message sending for {len(target_accounts)} accounts",
                results={"accounts": target_accounts, "mode": "full_with_sending"}
            )
        
        else:
            # Run analysis and reaction generation (no sending) in background
            background_tasks.add_task(
                _process_stories_no_sending,
                target_accounts
            )
            return TriggerResponse(
                success=True,
                message=f"Started processing without sending for {len(target_accounts)} accounts",
                results={"accounts": target_accounts, "mode": "no_sending"}
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in trigger endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Background task functions
async def _process_stories_analysis_only(target_accounts: List[str]):
    """Background task for analysis-only processing."""
    logger.info(f"Starting analysis-only processing for: {target_accounts}")
    
    scraper = InstagramScraper()
    analyzer = StoryAnalyzer()
    
    try:
        # Scrape stories
        await scraper.start()
        await scraper.login()
        stories_data = await scraper.scrape_multiple_users(target_accounts)
        
        # Analyze stories
        analyses = await analyzer.analyze_multiple_stories(stories_data)
        
        # Log results
        for username in target_accounts:
            user_stories = stories_data.get(username, [])
            user_analyses = analyses.get(username, [])
            
            logger.info(f"Analysis results for {username}:")
            logger.info(f"  - Stories found: {len(user_stories)}")
            logger.info(f"  - Stories analyzed: {len(user_analyses)}")
            
            for i, analysis in enumerate(user_analyses):
                logger.info(f"  - Story {i+1}: {analysis.mood} - {analysis.summary}")
    
    except Exception as e:
        logger.error(f"Error in analysis-only processing: {e}")
    
    finally:
        await scraper.close()


async def _process_stories_no_sending(target_accounts: List[str]):
    """Background task for processing without sending messages."""
    logger.info(f"Starting processing without sending for: {target_accounts}")
    
    scraper = InstagramScraper()
    analyzer = StoryAnalyzer()
    reply_generator = ReplyGenerator()
    
    try:
        # Scrape stories
        await scraper.start()
        await scraper.login()
        stories_data = await scraper.scrape_multiple_users(target_accounts)
        
        # Analyze stories
        analyses = await analyzer.analyze_multiple_stories(stories_data)
        
        # Generate reactions
        reactions = await reply_generator.generate_multiple_reactions(stories_data, analyses)
        
        # Log results
        for username in target_accounts:
            user_stories = stories_data.get(username, [])
            user_analyses = analyses.get(username, [])
            user_reactions = reactions.get(username, [])
            
            logger.info(f"Processing results for {username}:")
            logger.info(f"  - Stories found: {len(user_stories)}")
            logger.info(f"  - Stories analyzed: {len(user_analyses)}")
            logger.info(f"  - Reactions generated: {len(user_reactions)}")
            
            for i, reaction in enumerate(user_reactions):
                logger.info(f"  - Reaction {i+1}: '{reaction.text}' (confidence: {reaction.confidence:.2f})")
    
    except Exception as e:
        logger.error(f"Error in processing without sending: {e}")
    
    finally:
        await scraper.close()


async def _process_stories_with_sending(target_accounts: List[str]):
    """Background task for full processing with message sending."""
    logger.info(f"Starting full processing with sending for: {target_accounts}")
    
    scraper = InstagramScraper()
    analyzer = StoryAnalyzer()
    reply_generator = ReplyGenerator()
    dm_sender = DMSender(scraper)  # Reuse scraper session
    
    try:
        # Scrape stories
        await scraper.start()
        await scraper.login()
        stories_data = await scraper.scrape_multiple_users(target_accounts)
        
        # Analyze stories
        analyses = await analyzer.analyze_multiple_stories(stories_data)
        
        # Generate reactions
        reactions = await reply_generator.generate_multiple_reactions(stories_data, analyses)
        
        # Send DMs
        await dm_sender.initialize()
        send_results = await dm_sender.send_multiple_dms(reactions)
        
        # Log results
        total_sent = 0
        total_failed = 0
        
        for username in target_accounts:
            user_stories = stories_data.get(username, [])
            user_analyses = analyses.get(username, [])
            user_reactions = reactions.get(username, [])
            user_send_results = send_results.get(username, [])
            
            sent_count = sum(1 for result in user_send_results if result.success)
            failed_count = len(user_send_results) - sent_count
            
            total_sent += sent_count
            total_failed += failed_count
            
            logger.info(f"Full processing results for {username}:")
            logger.info(f"  - Stories found: {len(user_stories)}")
            logger.info(f"  - Stories analyzed: {len(user_analyses)}")
            logger.info(f"  - Reactions generated: {len(user_reactions)}")
            logger.info(f"  - Messages sent: {sent_count}")
            logger.info(f"  - Messages failed: {failed_count}")
            
            # Log individual reaction details
            for i, (reaction, send_result) in enumerate(zip(user_reactions, user_send_results)):
                status = "✓ SENT" if send_result.success else "✗ FAILED"
                logger.info(f"  - Reaction {i+1}: '{reaction.text[:30]}...' - {status}")
                if not send_result.success:
                    logger.error(f"    Error: {send_result.error}")
        
        logger.info(f"Full processing completed. Total sent: {total_sent}, Total failed: {total_failed}")
    
    except Exception as e:
        logger.error(f"Error in full processing with sending: {e}")
    
    finally:
        await scraper.close()


# Additional utility endpoint for testing
@router.get("/accounts")
async def get_target_accounts():
    """Get currently configured target accounts."""
    return {
        "target_accounts": settings.target_accounts_list,
        "count": len(settings.target_accounts_list)
    }


@router.get("/config")
async def get_config():
    """Get current configuration (without sensitive data)."""
    return {
        "environment": settings.environment,
        "log_level": settings.log_level,
        "headless_browser": settings.headless_browser,
        "browser_timeout": settings.browser_timeout,
        "target_accounts_count": len(settings.target_accounts_list),
        "redis_configured": bool(settings.redis_url),
        "instagram_configured": bool(settings.instagram_username and settings.instagram_password),
        "openai_configured": bool(settings.openai_api_key)
    }
