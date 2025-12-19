"""
AI story analyzer using OpenAI Vision API.
Analyzes Instagram story content (images and text) to understand context and mood.
"""

import base64
from typing import Dict, List, Optional, Any
from src.services.scraper import StoryData
from config.openai_config import openai_config
from src.utils.logger import logger


class StoryAnalysis:
    """Data class for story analysis results."""
    
    def __init__(self):
        self.mood: str = ""  # happy, sad, excited, neutral, etc.
        self.topics: List[str] = []  # main topics/themes
        self.objects: List[str] = []  # detected objects in image
        self.activity: str = ""  # what the person is doing
        self.location_context: str = ""  # indoor, outdoor, restaurant, etc.
        self.summary: str = ""  # brief description
        self.confidence_score: float = 0.0  # AI confidence (0-1)
        self.reaction_appropriateness: str = ""  # suggested reaction type


class StoryAnalyzer:
    """AI-powered story content analyzer."""
    
    def __init__(self):
        self.client = openai_config.client
        
        # Analysis prompts
        self.vision_prompt = """
        Analyze this Instagram story image and provide insights about:
        1. Mood/emotion of the person or overall vibe
        2. Main objects, people, or elements visible
        3. Activity or context (what's happening)
        4. Location type (indoor/outdoor/restaurant/gym/etc.)
        5. Overall summary in 1-2 sentences
        
        Be concise and friendly in your analysis. Focus on details that would help a friend write a natural, caring response.
        """
        
        self.text_analysis_prompt = """
        Analyze this Instagram story text and determine:
        1. Emotional tone/mood
        2. Main topics or themes
        3. What kind of response would be most appropriate
        4. Brief summary
        
        Text: {text}
        
        Provide a friendly analysis that helps understand how to respond naturally as a friend.
        """
        
    async def analyze_story(self, story_data: StoryData) -> StoryAnalysis:
        """Analyze a single story and return comprehensive insights."""
        analysis = StoryAnalysis()
        
        try:
            # Analyze visual content if available
            if story_data.image_data:
                visual_analysis = await self._analyze_visual_content(story_data.image_data)
                self._merge_visual_analysis(analysis, visual_analysis)
            
            # Analyze text content if available
            if story_data.text:
                text_analysis = await self._analyze_text_content(story_data.text)
                self._merge_text_analysis(analysis, text_analysis)
            
            # Generate overall summary
            analysis.summary = await self._generate_summary(story_data, analysis)
            
            # Determine appropriate reaction type
            analysis.reaction_appropriateness = self._determine_reaction_type(analysis)
            
            logger.info(f"Successfully analyzed story from {story_data.username}")
            
        except Exception as e:
            logger.error(f"Error analyzing story from {story_data.username}: {e}")
            # Return default analysis
            analysis.mood = "neutral"
            analysis.summary = f"Story from {story_data.username}"
            analysis.confidence_score = 0.1
            
        return analysis
    
    async def _analyze_visual_content(self, image_data: str) -> Dict[str, Any]:
        """Analyze image content using OpenAI Vision API."""
        try:
            logger.info("Analyzing visual content with OpenAI Vision")
            
            response = await self.client.chat.completions.create(
                model=openai_config.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": self.vision_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=openai_config.max_tokens,
                temperature=openai_config.temperature
            )
            
            content = response.choices[0].message.content
            return self._parse_vision_response(content)
            
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return {
                "mood": "neutral",
                "objects": [],
                "activity": "unknown",
                "location_context": "unknown",
                "summary": "Could not analyze image"
            }
    
    async def _analyze_text_content(self, text: str) -> Dict[str, Any]:
        """Analyze text content using OpenAI GPT."""
        try:
            logger.info("Analyzing text content with OpenAI GPT")
            
            response = await self.client.chat.completions.create(
                model=openai_config.text_model,
                messages=[
                    {
                        "role": "user",
                        "content": self.text_analysis_prompt.format(text=text)
                    }
                ],
                max_tokens=openai_config.max_tokens,
                temperature=openai_config.temperature
            )
            
            content = response.choices[0].message.content
            return self._parse_text_response(content, text)
            
        except Exception as e:
            logger.error(f"Text analysis failed: {e}")
            return {
                "mood": "neutral",
                "topics": [text[:50] + "..." if len(text) > 50 else text],
                "summary": text
            }
    
    def _parse_vision_response(self, response: str) -> Dict[str, Any]:
        """Parse OpenAI Vision API response."""
        # Simple parsing - in production, you might want more sophisticated parsing
        lines = response.lower().split('\n')
        
        result = {
            "mood": "neutral",
            "objects": [],
            "activity": "",
            "location_context": "",
            "summary": response[:100] + "..." if len(response) > 100 else response
        }
        
        # Extract mood keywords
        mood_keywords = ["happy", "sad", "excited", "calm", "energetic", "relaxed", "joyful", "peaceful"]
        for keyword in mood_keywords:
            if keyword in response.lower():
                result["mood"] = keyword
                break
        
        # Extract location context
        location_keywords = {
            "outdoor": ["outdoor", "outside", "park", "street", "nature"],
            "indoor": ["indoor", "inside", "home", "room"],
            "restaurant": ["restaurant", "cafe", "eating", "dining"],
            "gym": ["gym", "fitness", "workout", "exercise"],
            "beach": ["beach", "ocean", "sand", "water"]
        }
        
        for location, keywords in location_keywords.items():
            for keyword in keywords:
                if keyword in response.lower():
                    result["location_context"] = location
                    break
            if result["location_context"]:
                break
        
        return result
    
    def _parse_text_response(self, response: str, original_text: str) -> Dict[str, Any]:
        """Parse OpenAI text analysis response."""
        return {
            "mood": self._extract_mood_from_text(response),
            "topics": [original_text[:30] + "..." if len(original_text) > 30 else original_text],
            "summary": response[:100] + "..." if len(response) > 100 else response
        }
    
    def _extract_mood_from_text(self, text: str) -> str:
        """Extract mood from text analysis."""
        mood_map = {
            "positive": ["happy", "great", "awesome", "amazing", "love", "excited"],
            "negative": ["sad", "bad", "terrible", "awful", "hate", "depressed"],
            "neutral": ["okay", "fine", "normal", "usual"]
        }
        
        text_lower = text.lower()
        for mood, keywords in mood_map.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return mood
        
        return "neutral"
    
    def _merge_visual_analysis(self, analysis: StoryAnalysis, visual_data: Dict[str, Any]):
        """Merge visual analysis results into main analysis."""
        analysis.mood = visual_data.get("mood", "neutral")
        analysis.objects = visual_data.get("objects", [])
        analysis.activity = visual_data.get("activity", "")
        analysis.location_context = visual_data.get("location_context", "")
        
        if not analysis.summary:
            analysis.summary = visual_data.get("summary", "")
        
        analysis.confidence_score = 0.8  # High confidence for vision analysis
    
    def _merge_text_analysis(self, analysis: StoryAnalysis, text_data: Dict[str, Any]):
        """Merge text analysis results into main analysis."""
        # Text analysis might override or enhance visual analysis
        text_mood = text_data.get("mood", "neutral")
        if text_mood != "neutral":
            analysis.mood = text_mood
        
        analysis.topics.extend(text_data.get("topics", []))
        
        # Enhance summary with text insights
        text_summary = text_data.get("summary", "")
        if text_summary and analysis.summary:
            analysis.summary += f" Text: {text_summary}"
        elif text_summary:
            analysis.summary = text_summary
        
        # Increase confidence if we have both visual and text data
        if analysis.confidence_score > 0:
            analysis.confidence_score = min(0.95, analysis.confidence_score + 0.1)
        else:
            analysis.confidence_score = 0.7
    
    async def _generate_summary(self, story_data: StoryData, analysis: StoryAnalysis) -> str:
        """Generate a concise summary of the story."""
        if analysis.summary:
            return analysis.summary
        
        # Fallback summary generation
        summary_parts = []
        
        if story_data.username:
            summary_parts.append(f"{story_data.username}'s story")
        
        if analysis.mood != "neutral":
            summary_parts.append(f"showing {analysis.mood} mood")
        
        if analysis.activity:
            summary_parts.append(f"while {analysis.activity}")
        
        if analysis.location_context:
            summary_parts.append(f"at {analysis.location_context}")
        
        return " ".join(summary_parts) if summary_parts else "Instagram story"
    
    def _determine_reaction_type(self, analysis: StoryAnalysis) -> str:
        """Determine what type of reaction would be most appropriate."""
        mood_reactions = {
            "happy": "supportive_positive",
            "excited": "enthusiastic",
            "sad": "caring_supportive",
            "neutral": "casual_friendly",
            "positive": "supportive_positive",
            "negative": "caring_supportive"
        }
        
        return mood_reactions.get(analysis.mood, "casual_friendly")
    
    async def analyze_multiple_stories(self, stories_dict: Dict[str, List[StoryData]]) -> Dict[str, List[StoryAnalysis]]:
        """Analyze stories from multiple users."""
        results = {}
        
        for username, stories in stories_dict.items():
            logger.info(f"Analyzing {len(stories)} stories from {username}")
            user_analyses = []
            
            for story in stories:
                try:
                    analysis = await self.analyze_story(story)
                    user_analyses.append(analysis)
                except Exception as e:
                    logger.error(f"Failed to analyze story from {username}: {e}")
                    # Add a basic analysis for failed stories
                    failed_analysis = StoryAnalysis()
                    failed_analysis.mood = "neutral"
                    failed_analysis.summary = f"Failed to analyze story from {username}"
                    user_analyses.append(failed_analysis)
            
            results[username] = user_analyses
            
        return results


# Example usage and testing
async def test_analyzer():
    """Test the analyzer with mock data."""
    analyzer = StoryAnalyzer()
    
    # Create mock story data
    mock_story = StoryData(
        username="test_user",
        text="Having an amazing day at the beach! 🏖️☀️",
        story_type="text"
    )
    
    # Analyze the story
    analysis = await analyzer.analyze_story(mock_story)
    
    logger.info(f"Test analysis results:")
    logger.info(f"Mood: {analysis.mood}")
    logger.info(f"Topics: {analysis.topics}")
    logger.info(f"Summary: {analysis.summary}")
    logger.info(f"Reaction type: {analysis.reaction_appropriateness}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_analyzer())
