"""
Automated DM sender using Playwright browser automation.
Sends generated reactions via Instagram web interface.
"""

import asyncio
from typing import List, Dict, Optional, Tuple
from playwright.async_api import Page, Browser
from src.services.scraper import InstagramScraper
from src.services.reply_generator import ReactionResponse
from config.scraper_config import scraper_config
from src.utils.logger import logger


class DMSendResult:
    """Result of DM sending operation."""
    
    def __init__(self, username: str, success: bool, message: str = "", error: str = ""):
        self.username = username
        self.success = success
        self.message = message  # The message that was sent
        self.error = error
        self.timestamp = None


class DMSender:
    """Automated Instagram DM sender using browser automation."""
    
    def __init__(self, scraper: Optional[InstagramScraper] = None):
        """Initialize DM sender, optionally reusing an existing scraper."""
        self.scraper = scraper or InstagramScraper()
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        self._dm_selectors = {
            "search_box": "input[placeholder*='Search']",
            "user_result": "[role='button'] span",
            "message_button": "button:has-text('Message')",
            "message_input": "textarea[placeholder*='Message'], div[contenteditable='true'][role='textbox']",
            "send_button": "button:has-text('Send'), button[type='submit']",
            "dm_thread": "[role='main']",
            "new_message_button": "button:has-text('Send message')",
            "close_modal": "button[aria-label='Close']"
        }
    
    async def initialize(self):
        """Initialize the DM sender (login if needed)."""
        if not self.scraper.is_logged_in:
            await self.scraper.start()
            await self.scraper.login()
        
        self.page = self.scraper.page
        self.browser = self.scraper.browser
        logger.info("DM sender initialized")
    
    async def send_dm(self, username: str, message: str) -> DMSendResult:
        """Send a DM to a specific user."""
        if not self.page:
            await self.initialize()
        
        try:
            logger.info(f"Attempting to send DM to {username}")
            
            # Navigate to Instagram direct messages
            await self._navigate_to_dms()
            
            # Search for user
            user_found = await self._search_user(username)
            if not user_found:
                return DMSendResult(
                    username=username,
                    success=False,
                    error=f"Could not find user {username}"
                )
            
            # Open conversation
            conversation_opened = await self._open_conversation(username)
            if not conversation_opened:
                return DMSendResult(
                    username=username,
                    success=False,
                    error=f"Could not open conversation with {username}"
                )
            
            # Send message
            message_sent = await self._send_message(message)
            if not message_sent:
                return DMSendResult(
                    username=username,
                    success=False,
                    error="Failed to send message"
                )
            
            logger.info(f"Successfully sent DM to {username}: '{message[:50]}...'")
            return DMSendResult(
                username=username,
                success=True,
                message=message
            )
            
        except Exception as e:
            logger.error(f"Error sending DM to {username}: {e}")
            return DMSendResult(
                username=username,
                success=False,
                error=str(e)
            )
    
    async def _navigate_to_dms(self):
        """Navigate to Instagram Direct Messages."""
        try:
            # Try multiple approaches to get to DMs
            dm_urls = [
                f"{scraper_config.base_url}/direct/inbox/",
                f"{scraper_config.base_url}/direct/"
            ]
            
            for dm_url in dm_urls:
                await self.page.goto(dm_url)
                await self.page.wait_for_timeout(scraper_config.wait_times["page_load"])
                
                # Check if we're on the DMs page
                if "/direct/" in self.page.url:
                    logger.info("Successfully navigated to DMs")
                    return True
            
            # Alternative: Look for DM icon and click it
            dm_icon_selectors = [
                "a[href*='/direct/']",
                "svg[aria-label*='Messenger']",
                "[data-testid='new-post-button'] + a"  # DM icon is usually next to new post
            ]
            
            for selector in dm_icon_selectors:
                try:
                    dm_icon = self.page.locator(selector).first
                    if await dm_icon.is_visible(timeout=2000):
                        await dm_icon.click()
                        await self.page.wait_for_timeout(scraper_config.wait_times["navigation"])
                        if "/direct/" in self.page.url:
                            logger.info("Successfully navigated to DMs via icon")
                            return True
                except:
                    continue
                    
            raise Exception("Could not navigate to DMs")
            
        except Exception as e:
            logger.error(f"Failed to navigate to DMs: {e}")
            raise
    
    async def _search_user(self, username: str) -> bool:
        """Search for a user in DMs."""
        try:
            # Look for search box or new message button
            search_selectors = [
                self._dm_selectors["search_box"],
                "input[placeholder*='search']",
                "input[type='text']"
            ]
            
            search_box = None
            for selector in search_selectors:
                try:
                    search_box = self.page.locator(selector).first
                    if await search_box.is_visible(timeout=2000):
                        break
                except:
                    continue
            
            if not search_box or not await search_box.is_visible():
                # Try to click new message button first
                new_msg_selectors = [
                    self._dm_selectors["new_message_button"],
                    "button:has-text('Send message')",
                    "button:has-text('New message')",
                    "[aria-label*='New message']"
                ]
                
                for selector in new_msg_selectors:
                    try:
                        new_msg_btn = self.page.locator(selector).first
                        if await new_msg_btn.is_visible(timeout=2000):
                            await new_msg_btn.click()
                            await self.page.wait_for_timeout(scraper_config.wait_times["navigation"])
                            break
                    except:
                        continue
                
                # Try to find search box again
                for selector in search_selectors:
                    try:
                        search_box = self.page.locator(selector).first
                        if await search_box.is_visible(timeout=2000):
                            break
                    except:
                        continue
            
            if not search_box or not await search_box.is_visible():
                raise Exception("Could not find search box")
            
            # Type username
            await search_box.fill(username)
            await self.page.wait_for_timeout(1000)  # Wait for search results
            
            logger.info(f"Searched for user: {username}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to search for user {username}: {e}")
            return False
    
    async def _open_conversation(self, username: str) -> bool:
        """Open conversation with the searched user."""
        try:
            # Look for user in search results
            user_result_selectors = [
                f"text={username}",
                f"[title='{username}']",
                self._dm_selectors["user_result"],
                "[role='button'] img + div",  # Username next to profile pic
                f"span:has-text('{username}')"
            ]
            
            for selector in user_result_selectors:
                try:
                    user_result = self.page.locator(selector).first
                    if await user_result.is_visible(timeout=2000):
                        await user_result.click()
                        await self.page.wait_for_timeout(scraper_config.wait_times["navigation"])
                        
                        # Check if conversation opened (look for message input)
                        message_input = self.page.locator(self._dm_selectors["message_input"]).first
                        if await message_input.is_visible(timeout=3000):
                            logger.info(f"Successfully opened conversation with {username}")
                            return True
                except:
                    continue
            
            # Alternative: click the first result if exact match not found
            try:
                first_result = self.page.locator("[role='button']:has(img)").first
                if await first_result.is_visible(timeout=2000):
                    await first_result.click()
                    await self.page.wait_for_timeout(scraper_config.wait_times["navigation"])
                    
                    message_input = self.page.locator(self._dm_selectors["message_input"]).first
                    if await message_input.is_visible(timeout=3000):
                        logger.info(f"Opened conversation with first search result")
                        return True
            except:
                pass
                
            return False
            
        except Exception as e:
            logger.error(f"Failed to open conversation with {username}: {e}")
            return False
    
    async def _send_message(self, message: str) -> bool:
        """Send the actual message."""
        try:
            # Find message input
            message_input_selectors = [
                self._dm_selectors["message_input"],
                "textarea[placeholder*='Message']",
                "div[contenteditable='true'][role='textbox']",
                "textarea[aria-label*='Message']"
            ]
            
            message_input = None
            for selector in message_input_selectors:
                try:
                    message_input = self.page.locator(selector).first
                    if await message_input.is_visible(timeout=2000):
                        break
                except:
                    continue
            
            if not message_input or not await message_input.is_visible():
                raise Exception("Could not find message input field")
            
            # Type message
            await message_input.fill(message)
            await self.page.wait_for_timeout(500)  # Brief pause
            
            # Find and click send button
            send_button_selectors = [
                self._dm_selectors["send_button"],
                "button:has-text('Send')",
                "button[type='submit']",
                "[aria-label*='Send']",
                "button svg[aria-label*='Send']"
            ]
            
            for selector in send_button_selectors:
                try:
                    send_button = self.page.locator(selector).first
                    if await send_button.is_visible(timeout=2000):
                        await send_button.click()
                        await self.page.wait_for_timeout(1000)  # Wait for message to send
                        logger.info(f"Message sent: '{message[:50]}...'")
                        return True
                except:
                    continue
            
            # Alternative: try Enter key
            try:
                await message_input.press("Enter")
                await self.page.wait_for_timeout(1000)
                logger.info(f"Message sent via Enter key: '{message[:50]}...'")
                return True
            except:
                pass
                
            return False
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def send_multiple_dms(self, reactions: Dict[str, List[ReactionResponse]]) -> Dict[str, List[DMSendResult]]:
        """Send DMs to multiple users based on their story reactions."""
        results = {}
        
        for username, user_reactions in reactions.items():
            user_results = []
            
            for i, reaction in enumerate(user_reactions):
                try:
                    logger.info(f"Sending DM {i+1}/{len(user_reactions)} to {username}")
                    
                    # Send the primary reaction
                    result = await self.send_dm(username, reaction.text)
                    user_results.append(result)
                    
                    # If failed and we have backups, try them
                    if not result.success and reaction.backup_responses:
                        for backup in reaction.backup_responses[:2]:  # Try max 2 backups
                            logger.info(f"Trying backup response for {username}")
                            backup_result = await self.send_dm(username, backup)
                            if backup_result.success:
                                user_results[-1] = backup_result  # Replace failed result
                                break
                    
                    # Brief pause between messages to same user
                    if i < len(user_reactions) - 1:
                        await asyncio.sleep(2)
                        
                except Exception as e:
                    logger.error(f"Error sending DM {i+1} to {username}: {e}")
                    user_results.append(DMSendResult(
                        username=username,
                        success=False,
                        error=str(e)
                    ))
            
            results[username] = user_results
            
            # Pause between different users
            await asyncio.sleep(3)
        
        return results
    
    async def send_story_reactions(self, username: str, reaction: ReactionResponse) -> DMSendResult:
        """Send a reaction to a story (alternative to DM - could be story reply)."""
        # This is a simplified version - Instagram story replies might need different handling
        return await self.send_dm(username, f"Reacting to your story: {reaction.text}")
    
    async def close(self):
        """Close the DM sender and cleanup."""
        if self.scraper:
            await self.scraper.close()
        logger.info("DM sender closed")


# Example usage
async def test_dm_sender():
    """Test DM sending functionality."""
    from src.services.reply_generator import ReactionResponse
    
    sender = DMSender()
    
    try:
        await sender.initialize()
        
        # Test sending a single DM
        test_reaction = ReactionResponse(
            text="Hey! Just testing the auto-responder 😊",
            confidence=0.8
        )
        
        # Replace 'test_user' with an actual Instagram username for testing
        result = await sender.send_dm("test_user", test_reaction.text)
        
        logger.info(f"DM send result: {result.success}")
        if result.error:
            logger.error(f"Error: {result.error}")
            
    finally:
        await sender.close()


if __name__ == "__main__":
    # Uncomment to test (make sure you have valid Instagram credentials)
    # asyncio.run(test_dm_sender())
    logger.info("DM Sender module loaded. Use test_dm_sender() to test.")
