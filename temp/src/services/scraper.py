"""
Instagram story scraper using Playwright.
Handles login, navigation, and content extraction.
"""

import asyncio
import base64
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, Browser
from src.utils.env import settings
from src.utils.logger import logger
from config.scraper_config import scraper_config


class StoryData:
    """Data class for story content."""
    
    def __init__(self, username: str, image_data: Optional[str] = None, 
                 text: Optional[str] = None, story_type: str = "image"):
        self.username = username
        self.image_data = image_data  # Base64 encoded image
        self.text = text
        self.story_type = story_type  # 'image', 'video', 'text'
        self.timestamp = None


class InstagramScraper:
    """Instagram story scraper using Playwright."""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.is_logged_in = False
        
    async def start(self):
        """Initialize browser and page."""
        try:
            playwright = await async_playwright().start()
            
            # Launch browser
            self.browser = await playwright.chromium.launch(
                headless=scraper_config.headless,
                args=scraper_config.get_browser_args()
            )
            
            # Create page
            self.page = await self.browser.new_page(
                viewport=scraper_config.viewport
            )
            
            # Set timeout
            self.page.set_default_timeout(scraper_config.timeout)
            
            logger.info("Browser initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            raise
    
    async def login(self) -> bool:
        """Login to Instagram."""
        if not self.page:
            await self.start()
            
        try:
            logger.info("Attempting to login to Instagram")
            
            # Navigate to login page
            await self.page.goto(scraper_config.login_url)
            await self.page.wait_for_timeout(scraper_config.wait_times["page_load"])
            
            # Fill username
            await self.page.fill(
                scraper_config.selectors["username_input"],
                settings.instagram_username
            )
            
            # Fill password
            await self.page.fill(
                scraper_config.selectors["password_input"],
                settings.instagram_password
            )
            
            # Click login button
            await self.page.click(scraper_config.selectors["login_button"])
            
            # Wait for navigation
            await self.page.wait_for_timeout(scraper_config.wait_times["login"])
            
            # Check if login was successful
            current_url = self.page.url
            if "/accounts/login/" not in current_url:
                self.is_logged_in = True
                logger.info("Successfully logged into Instagram")
                return True
            else:
                logger.error("Login failed - still on login page")
                return False
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    async def navigate_to_user_stories(self, username: str) -> bool:
        """Navigate to a specific user's stories."""
        if not self.is_logged_in:
            await self.login()
            
        try:
            logger.info(f"Navigating to {username}'s stories")
            
            # Navigate to user profile
            profile_url = f"{scraper_config.base_url}/{username}/"
            await self.page.goto(profile_url)
            await self.page.wait_for_timeout(scraper_config.wait_times["page_load"])
            
            # Look for story ring/avatar (this selector may need updating)
            story_avatar = self.page.locator(f"img[alt='{username}\\'s profile picture']").first
            
            if await story_avatar.is_visible():
                await story_avatar.click()
                await self.page.wait_for_timeout(scraper_config.wait_times["story_load"])
                logger.info(f"Successfully opened {username}'s stories")
                return True
            else:
                logger.warning(f"No active stories found for {username}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to navigate to {username}'s stories: {e}")
            return False
    
    async def extract_story_content(self) -> Optional[StoryData]:
        """Extract content from current story."""
        try:
            # Wait for story content to load
            await self.page.wait_for_timeout(scraper_config.wait_times["story_load"])
            
            # Get username from story header
            username_element = self.page.locator(scraper_config.selectors["story_user_link"]).first
            username = await username_element.get_attribute("href")
            if username:
                username = username.split("/")[1] if "/" in username else "unknown"
            else:
                username = "unknown"
            
            # Try to extract image
            image_data = None
            story_type = "image"
            
            image_element = self.page.locator(scraper_config.selectors["story_image"]).first
            if await image_element.is_visible():
                # Get image as base64
                image_data = await self._capture_element_screenshot(image_element)
                story_type = "image"
            else:
                # Check for video
                video_element = self.page.locator(scraper_config.selectors["story_video"]).first
                if await video_element.is_visible():
                    # For video, capture a frame
                    image_data = await self._capture_element_screenshot(video_element)
                    story_type = "video"
            
            # Try to extract text
            text_content = None
            text_elements = self.page.locator(scraper_config.selectors["story_text"])
            if await text_elements.count() > 0:
                text_parts = []
                for i in range(await text_elements.count()):
                    text = await text_elements.nth(i).inner_text()
                    if text.strip():
                        text_parts.append(text.strip())
                text_content = " ".join(text_parts) if text_parts else None
            
            story_data = StoryData(
                username=username,
                image_data=image_data,
                text=text_content,
                story_type=story_type
            )
            
            logger.info(f"Extracted story content from {username}")
            return story_data
            
        except Exception as e:
            logger.error(f"Failed to extract story content: {e}")
            return None
    
    async def _capture_element_screenshot(self, element) -> Optional[str]:
        """Capture screenshot of an element and return as base64."""
        try:
            screenshot = await element.screenshot()
            return base64.b64encode(screenshot).decode()
        except Exception as e:
            logger.error(f"Failed to capture element screenshot: {e}")
            return None
    
    async def scrape_user_stories(self, username: str) -> List[StoryData]:
        """Scrape all stories from a specific user."""
        stories = []
        
        if not await self.navigate_to_user_stories(username):
            return stories
        
        try:
            # Extract current story
            story_data = await self.extract_story_content()
            if story_data:
                stories.append(story_data)
            
            # Try to navigate to next stories
            story_count = 1
            max_stories = 10  # Limit to prevent infinite loops
            
            while story_count < max_stories:
                try:
                    # Click next button
                    next_button = self.page.locator(scraper_config.selectors["next_story"]).first
                    if await next_button.is_visible():
                        await next_button.click()
                        await self.page.wait_for_timeout(scraper_config.wait_times["navigation"])
                        
                        # Extract next story
                        story_data = await self.extract_story_content()
                        if story_data:
                            stories.append(story_data)
                        story_count += 1
                    else:
                        break
                        
                except Exception as e:
                    logger.warning(f"Error navigating to next story: {e}")
                    break
            
            logger.info(f"Scraped {len(stories)} stories from {username}")
            
        except Exception as e:
            logger.error(f"Error scraping stories from {username}: {e}")
        
        return stories
    
    async def scrape_multiple_users(self, usernames: List[str]) -> Dict[str, List[StoryData]]:
        """Scrape stories from multiple users."""
        results = {}
        
        for username in usernames:
            logger.info(f"Starting to scrape stories for {username}")
            try:
                stories = await self.scrape_user_stories(username)
                results[username] = stories
            except Exception as e:
                logger.error(f"Failed to scrape stories for {username}: {e}")
                results[username] = []
        
        return results
    
    async def close(self):
        """Close browser and cleanup."""
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            logger.info("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")


# Example usage
async def main():
    """Example usage of the scraper."""
    scraper = InstagramScraper()
    
    try:
        await scraper.start()
        await scraper.login()
        
        # Scrape stories from target accounts
        target_accounts = settings.target_accounts_list
        if target_accounts:
            results = await scraper.scrape_multiple_users(target_accounts)
            
            for username, stories in results.items():
                logger.info(f"{username}: {len(stories)} stories")
                for story in stories:
                    logger.info(f"  - {story.story_type}: {story.text[:50] if story.text else 'No text'}")
        
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
