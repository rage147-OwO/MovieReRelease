"""
Environment configuration management for AiMate.
Loads and validates environment variables using pydantic-settings.
"""

from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Instagram credentials
    instagram_username: str
    instagram_password: str
    
    # OpenAI API
    openai_api_key: str
    
    # Target accounts to monitor
    target_accounts: str = ""  # Comma-separated string
    
    # App settings
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "localhost"
    port: int = 8000
    
    # Redis (optional)
    redis_url: Optional[str] = None
    
    # Instagram settings
    headless_browser: bool = True
    browser_timeout: int = 30000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @property
    def target_accounts_list(self) -> List[str]:
        """Convert comma-separated target_accounts string to list."""
        if not self.target_accounts:
            return []
        return [account.strip() for account in self.target_accounts.split(",")]


# Global settings instance
settings = Settings()
