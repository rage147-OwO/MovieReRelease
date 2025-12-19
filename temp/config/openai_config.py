"""
OpenAI configuration and client setup for AiMate.
"""

from openai import AsyncOpenAI
from src.utils.env import settings
from src.utils.logger import logger


class OpenAIConfig:
    """OpenAI configuration and client management."""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.vision_model = "gpt-4-vision-preview"
        self.text_model = "gpt-4"
        
        # Vision API settings
        self.max_tokens = 300
        self.temperature = 0.7
        
        logger.info("OpenAI client initialized")
    
    async def test_connection(self) -> bool:
        """Test OpenAI API connection."""
        try:
            response = await self.client.chat.completions.create(
                model=self.text_model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            logger.info("OpenAI connection test successful")
            return True
        except Exception as e:
            logger.error(f"OpenAI connection test failed: {e}")
            return False


# Global OpenAI config instance
openai_config = OpenAIConfig()
