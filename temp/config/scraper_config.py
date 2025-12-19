"""
Playwright scraper configuration for Instagram.
"""

from playwright.async_api import BrowserType
from src.utils.env import settings
from src.utils.logger import logger


class ScraperConfig:
    """Configuration for Instagram scraper."""
    
    def __init__(self):
        # Browser settings
        self.headless = settings.headless_browser
        self.timeout = settings.browser_timeout
        self.viewport = {"width": 1280, "height": 720}
        
        # Instagram URLs
        self.base_url = "https://www.instagram.com"
        self.login_url = f"{self.base_url}/accounts/login/"
        self.stories_url = f"{self.base_url}/stories"
        
        # Selectors (may need updates as Instagram changes)
        self.selectors = {
            "username_input": "input[name='username']",
            "password_input": "input[name='password']",
            "login_button": "button[type='submit']",
            "story_image": "img[style*='object-fit']",
            "story_video": "video",
            "story_text": "[data-testid='story-viewer-text']",
            "next_story": "button[aria-label='Next']",
            "close_story": "button[aria-label='Close']",
            "story_user_link": "a[role='link']",
            "dm_button": "button[aria-label*='Message']",
            "message_input": "textarea[placeholder*='Message']",
            "send_button": "button[type='submit']"
        }
        
        # Wait times (in milliseconds)
        self.wait_times = {
            "page_load": 5000,
            "login": 3000,
            "story_load": 2000,
            "navigation": 1000
        }
        
        logger.info("Scraper configuration initialized")
    
    def get_browser_args(self) -> list:
        """Get browser launch arguments."""
        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--disable-gpu"
        ]
        
        if not self.headless:
            args.extend([
                "--start-maximized",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor"
            ])
        
        return args


# Global scraper config instance
scraper_config = ScraperConfig()
