"""
Optional Redis queue implementation for AiMate.
Handles story processing tasks in a queue for better scalability.
"""

import asyncio
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
import redis.asyncio as redis
from src.utils.env import settings
from src.utils.logger import logger


class TaskQueue:
    """Redis-based task queue for story processing."""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.queue_name = "aimate:story_tasks"
        self.result_key_prefix = "aimate:result:"
        self.is_connected = False
    
    async def connect(self) -> bool:
        """Connect to Redis."""
        if not settings.redis_url:
            logger.warning("Redis URL not configured, queue functionality disabled")
            return False
        
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # Test connection
            await self.redis_client.ping()
            self.is_connected = True
            logger.info("Connected to Redis successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.is_connected = False
            return False
    
    async def add_task(self, task_type: str, data: Dict[str, Any], priority: int = 0) -> str:
        """Add a task to the queue."""
        if not self.is_connected:
            raise RuntimeError("Redis not connected")
        
        task_id = f"task_{datetime.utcnow().timestamp()}_{task_type}"
        task_data = {
            "id": task_id,
            "type": task_type,
            "data": data,
            "priority": priority,
            "created_at": datetime.utcnow().isoformat(),
            "status": "pending"
        }
        
        try:
            # Add to queue (using list for simplicity, could use sorted sets for priority)
            await self.redis_client.lpush(self.queue_name, json.dumps(task_data))
            logger.info(f"Added task {task_id} to queue")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to add task to queue: {e}")
            raise
    
    async def get_task(self, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """Get next task from queue."""
        if not self.is_connected:
            return None
        
        try:
            # Blocking pop with timeout
            result = await self.redis_client.brpop(self.queue_name, timeout=timeout)
            if result:
                queue_name, task_json = result
                task_data = json.loads(task_json)
                logger.info(f"Retrieved task {task_data['id']} from queue")
                return task_data
            return None
            
        except Exception as e:
            logger.error(f"Failed to get task from queue: {e}")
            return None
    
    async def update_task_status(self, task_id: str, status: str, result: Optional[Dict[str, Any]] = None):
        """Update task status and store result."""
        if not self.is_connected:
            return
        
        try:
            result_data = {
                "task_id": task_id,
                "status": status,
                "updated_at": datetime.utcnow().isoformat(),
                "result": result or {}
            }
            
            result_key = f"{self.result_key_prefix}{task_id}"
            await self.redis_client.setex(
                result_key, 
                86400,  # Expire after 24 hours
                json.dumps(result_data)
            )
            
            logger.info(f"Updated task {task_id} status to {status}")
            
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
    
    async def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task result by ID."""
        if not self.is_connected:
            return None
        
        try:
            result_key = f"{self.result_key_prefix}{task_id}"
            result_json = await self.redis_client.get(result_key)
            
            if result_json:
                return json.loads(result_json)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get task result: {e}")
            return None
    
    async def queue_story_processing(self, accounts: List[str], send_messages: bool = False) -> str:
        """Queue a story processing task."""
        task_data = {
            "accounts": accounts,
            "send_messages": send_messages,
            "requested_at": datetime.utcnow().isoformat()
        }
        
        return await self.add_task("story_processing", task_data)
    
    async def get_queue_size(self) -> int:
        """Get current queue size."""
        if not self.is_connected:
            return 0
        
        try:
            return await self.redis_client.llen(self.queue_name)
        except Exception as e:
            logger.error(f"Failed to get queue size: {e}")
            return 0
    
    async def clear_queue(self):
        """Clear all tasks from queue (admin function)."""
        if not self.is_connected:
            return
        
        try:
            await self.redis_client.delete(self.queue_name)
            logger.info("Cleared task queue")
        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")
    
    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            self.is_connected = False
            logger.info("Redis connection closed")


# Global queue instance
task_queue = TaskQueue()


async def init_queue():
    """Initialize the task queue."""
    return await task_queue.connect()


# Task processor function
async def process_queue_tasks():
    """Process tasks from the queue continuously."""
    # Import here to avoid circular imports
    try:
        from src.services.scraper import InstagramScraper
        from src.services.analyzer import StoryAnalyzer
        from src.services.reply_generator import ReplyGenerator
        from src.services.dm_sender import DMSender
    except ImportError as e:
        logger.error(f"Failed to import services: {e}")
        return
    
    if not task_queue.is_connected:
        logger.error("Cannot process tasks: Redis not connected")
        return
    
    logger.info("Starting task queue processor")
    
    while True:
        try:
            # Get next task
            task = await task_queue.get_task(timeout=30)
            if not task:
                continue  # Timeout, check again
            
            task_id = task["id"]
            task_type = task["type"]
            
            logger.info(f"Processing task {task_id} of type {task_type}")
            await task_queue.update_task_status(task_id, "processing")
            
            if task_type == "story_processing":
                await _process_story_task(task)
            else:
                logger.warning(f"Unknown task type: {task_type}")
                await task_queue.update_task_status(task_id, "failed", {"error": "Unknown task type"})
        
        except Exception as e:
            logger.error(f"Error processing task: {e}")
            if 'task' in locals() and 'task_id' in locals():
                await task_queue.update_task_status(task_id, "failed", {"error": str(e)})


async def _process_story_task(task: Dict[str, Any]):
    """Process a story processing task."""
    # Import here to avoid circular imports
    try:
        from src.services.scraper import InstagramScraper
        from src.services.analyzer import StoryAnalyzer
        from src.services.reply_generator import ReplyGenerator
        from src.services.dm_sender import DMSender
    except ImportError as e:
        logger.error(f"Failed to import services: {e}")
        return
    
    task_id = task["id"]
    accounts = task["data"]["accounts"]
    send_messages = task["data"].get("send_messages", False)
    
    result = {
        "accounts_processed": 0,
        "total_stories": 0,
        "total_reactions": 0,
        "messages_sent": 0,
        "errors": []
    }
    
    scraper = InstagramScraper()
    analyzer = StoryAnalyzer()
    reply_generator = ReplyGenerator()
    dm_sender = None
    
    try:
        # Initialize services
        await scraper.start()
        await scraper.login()
        
        if send_messages:
            dm_sender = DMSender(scraper)
            await dm_sender.initialize()
        
        # Process each account
        for account in accounts:
            try:
                logger.info(f"Processing stories for {account}")
                
                # Scrape stories
                stories = await scraper.scrape_user_stories(account)
                result["total_stories"] += len(stories)
                
                if stories:
                    # Analyze stories
                    analyses = []
                    for story in stories:
                        analysis = await analyzer.analyze_story(story)
                        analyses.append(analysis)
                    
                    # Generate reactions
                    reactions = []
                    for story, analysis in zip(stories, analyses):
                        reaction = await reply_generator.generate_reaction(story, analysis)
                        reactions.append(reaction)
                    
                    result["total_reactions"] += len(reactions)
                    
                    # Send messages if requested
                    if send_messages and dm_sender:
                        for reaction in reactions:
                            dm_result = await dm_sender.send_dm(account, reaction.text)
                            if dm_result.success:
                                result["messages_sent"] += 1
                
                result["accounts_processed"] += 1
                
            except Exception as e:
                error_msg = f"Error processing {account}: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
        
        await task_queue.update_task_status(task_id, "completed", result)
        logger.info(f"Completed task {task_id}")
        
    except Exception as e:
        error_msg = f"Failed to process story task: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        await task_queue.update_task_status(task_id, "failed", result)
        
    finally:
        # Cleanup
        if scraper:
            await scraper.close()


# Example usage
async def example_queue_usage():
    """Example of how to use the task queue."""
    # Initialize queue
    connected = await init_queue()
    if not connected:
        logger.info("Queue not available, skipping example")
        return
    
    # Add a task
    task_id = await task_queue.queue_story_processing(
        accounts=["test_user1", "test_user2"],
        send_messages=False
    )
    
    logger.info(f"Queued task: {task_id}")
    
    # Check queue size
    size = await task_queue.get_queue_size()
    logger.info(f"Queue size: {size}")
    
    # You would run process_queue_tasks() in a separate process/worker


if __name__ == "__main__":
    # Run example
    asyncio.run(example_queue_usage())
