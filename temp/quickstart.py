#!/usr/bin/env python3
"""
Quick start script for AiMate development.
This script helps set up the environment and run basic tests.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path so we can import modules
sys.path.append(str(Path(__file__).parent / "src"))

async def main():
    """Main entry point for the quick start script."""
    print("🤖 AiMate Quick Start Script")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not Path(".env.example").exists():
        print("❌ Error: Run this script from the AiMate project root directory")
        sys.exit(1)
    
    # Check if .env file exists
    if not Path(".env").exists():
        print("📝 No .env file found. Creating from .env.example...")
        try:
            with open(".env.example", "r") as src, open(".env", "w") as dst:
                dst.write(src.read())
            print("✅ Created .env file. Please edit it with your credentials.")
            print("   Required: INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, OPENAI_API_KEY")
            return
        except Exception as e:
            print(f"❌ Error creating .env file: {e}")
            return
    
    print("✅ Found .env file")
    
    # Test environment loading
    print("\n🔧 Testing configuration...")
    try:
        from src.utils.env import settings
        print(f"   Environment: {settings.environment}")
        print(f"   Log level: {settings.log_level}")
        print(f"   Target accounts: {len(settings.target_accounts_list)}")
        print(f"   Instagram configured: {bool(settings.instagram_username and settings.instagram_password)}")
        print(f"   OpenAI configured: {bool(settings.openai_api_key)}")
        print(f"   Redis configured: {bool(settings.redis_url)}")
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        return
    
    # Test OpenAI connection
    if settings.openai_api_key:
        print("\n🤖 Testing OpenAI connection...")
        try:
            from config.openai_config import openai_config
            connected = await openai_config.test_connection()
            if connected:
                print("✅ OpenAI connection successful")
            else:
                print("❌ OpenAI connection failed")
        except Exception as e:
            print(f"❌ Error testing OpenAI: {e}")
    else:
        print("\n⚠️  OpenAI API key not configured - skipping connection test")
    
    # Test basic functionality
    if settings.instagram_username and settings.instagram_password and settings.openai_api_key:
        print("\n🧪 Running basic functionality test...")
        
        # Test story analyzer with mock data
        try:
            from src.services.analyzer import StoryAnalyzer, StoryAnalysis
            from src.services.scraper import StoryData
            from src.services.reply_generator import ReplyGenerator
            
            # Create mock story
            mock_story = StoryData(
                username="test_user",
                text="Having a great day! ☀️",
                story_type="text"
            )
            
            # Test analyzer
            analyzer = StoryAnalyzer()
            analysis = await analyzer.analyze_story(mock_story)
            print(f"   📊 Story analysis: {analysis.mood} - {analysis.summary}")
            
            # Test reply generator
            generator = ReplyGenerator()
            reaction = await generator.generate_reaction(mock_story, analysis)
            print(f"   💬 Generated reaction: '{reaction.text}' (confidence: {reaction.confidence:.2f})")
            
            print("✅ Basic functionality test passed!")
            
        except Exception as e:
            print(f"❌ Basic functionality test failed: {e}")
    else:
        print("\n⚠️  Missing credentials - skipping functionality test")
    
    print("\n🚀 Setup complete! Here's what you can do next:")
    print("\n1. Start the FastAPI server:")
    print("   python -m uvicorn src.main:app --reload")
    print("\n2. Test the health endpoint:")
    print("   curl http://localhost:8000/api/v1/health")
    print("\n3. Manually trigger story processing:")
    print("   curl -X POST http://localhost:8000/api/v1/trigger")
    print("\n4. View API documentation:")
    print("   Open http://localhost:8000/docs in your browser")
    print("\n5. For Instagram scraping tests, make sure you have:")
    print("   - Valid Instagram credentials in .env")
    print("   - Target accounts configured")
    print("   - Playwright browser installed: playwright install chromium")


if __name__ == "__main__":
    asyncio.run(main())
