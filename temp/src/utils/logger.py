"""
Logging configuration for AiMate using loguru.
Provides structured logging with rotation and filtering.
"""

import sys
from loguru import logger
from src.utils.env import settings


def setup_logging():
    """Configure loguru logger with appropriate settings."""
    
    # Remove default logger
    logger.remove()
    
    # Add console logger with custom format
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        colorize=True
    )
    
    # Add file logger with rotation
    logger.add(
        "logs/aimate.log",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="10 MB",
        retention="30 days",
        compression="zip"
    )
    
    return logger


# Initialize logger
logger = setup_logging()
