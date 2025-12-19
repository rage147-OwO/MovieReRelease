"""
GPT-based natural reaction generator for Instagram stories.
Generates friend-like, natural responses based on story analysis.
"""

from typing import Dict, List, Optional
from src.services.analyzer import StoryAnalysis
from src.services.scraper import StoryData
from config.openai_config import openai_config
from src.utils.logger import logger


class ReactionResponse:
    """Data class for generated reaction responses."""
    
    def __init__(self, text: str, confidence: float = 0.0, reaction_type: str = "comment"):
        self.text = text
        self.confidence = confidence
        self.reaction_type = reaction_type  # 'comment', 'dm', 'emoji_only'
        self.backup_responses: List[str] = []


class ReplyGenerator:
    """AI-powered natural reply generator for Instagram stories."""
    
    def __init__(self):
        self.client = openai_config.client
        
        # Base prompt for generating natural reactions
        self.base_prompt = """
        You are a close friend responding to an Instagram story. Generate a natural, caring, and authentic response.
        
        Story Context:
        - From: {username}
        - Mood: {mood}
        - Activity: {activity}
        - Location: {location}
        - Summary: {summary}
        {text_content}
        
        Reaction Style: {reaction_style}
        
        Guidelines:
        1. Keep it short and natural (1-2 sentences max)
        2. Use casual, friendly language
        3. Show genuine interest and care
        4. Avoid being overly enthusiastic unless appropriate
        5. Match the energy level of the story
        6. Use emojis sparingly and naturally
        7. Don't mention you're an AI
        
        Generate a {response_type} that feels like it comes from a real friend:
        """
        
        # Reaction style templates based on mood and context
        self.reaction_styles = {
            "supportive_positive": "Be encouraging and share their happiness. Show excitement for them.",
            "enthusiastic": "Match their energy with enthusiasm. Be genuinely excited.",
            "caring_supportive": "Be gentle and supportive. Show you care and are there for them.",
            "casual_friendly": "Keep it light and friendly. Make a casual, warm comment.",
            "playful": "Be playful and fun. Maybe tease them gently in a friendly way.",
            "concerned": "Show gentle concern and care. Ask if they're okay."
        }
    
    async def generate_reaction(self, story_data: StoryData, analysis: StoryAnalysis, 
                              response_type: str = "comment") -> ReactionResponse:
        """Generate a natural reaction to a story."""
        try:
            logger.info(f"Generating {response_type} reaction for {story_data.username}")
            
            # Determine reaction style
            reaction_style = self._get_reaction_style(analysis)
            
            # Prepare context
            context = self._prepare_context(story_data, analysis)
            
            # Generate primary response
            prompt = self._build_prompt(context, reaction_style, response_type)
            primary_response = await self._generate_response(prompt)
            
            # Generate backup responses
            backup_responses = await self._generate_backup_responses(context, reaction_style, response_type)
            
            # Create reaction response
            reaction = ReactionResponse(
                text=primary_response,
                confidence=self._calculate_confidence(analysis),
                reaction_type=response_type
            )
            reaction.backup_responses = backup_responses
            
            logger.info(f"Generated reaction: '{primary_response[:50]}...'")
            return reaction
            
        except Exception as e:
            logger.error(f"Failed to generate reaction for {story_data.username}: {e}")
            return self._generate_fallback_reaction(story_data, response_type)
    
    def _get_reaction_style(self, analysis: StoryAnalysis) -> str:
        """Determine the appropriate reaction style based on analysis."""
        style_map = {
            "happy": "supportive_positive",
            "excited": "enthusiastic", 
            "joyful": "enthusiastic",
            "sad": "caring_supportive",
            "negative": "caring_supportive",
            "calm": "casual_friendly",
            "peaceful": "casual_friendly",
            "energetic": "enthusiastic",
            "neutral": "casual_friendly"
        }
        
        base_style = style_map.get(analysis.mood, "casual_friendly")
        
        # Adjust based on context
        if "workout" in analysis.activity.lower() or "gym" in analysis.location_context.lower():
            return "supportive_positive"
        elif "beach" in analysis.location_context.lower() or "vacation" in analysis.summary.lower():
            return "enthusiastic"
        
        return base_style
    
    def _prepare_context(self, story_data: StoryData, analysis: StoryAnalysis) -> Dict[str, str]:
        """Prepare context information for prompt generation."""
        return {
            "username": story_data.username,
            "mood": analysis.mood,
            "activity": analysis.activity or "unknown activity",
            "location": analysis.location_context or "unknown location",
            "summary": analysis.summary,
            "text_content": f"Text in story: \"{story_data.text}\"" if story_data.text else "No text in story"
        }
    
    def _build_prompt(self, context: Dict[str, str], reaction_style: str, response_type: str) -> str:
        """Build the complete prompt for GPT."""
        style_description = self.reaction_styles.get(reaction_style, self.reaction_styles["casual_friendly"])
        
        return self.base_prompt.format(
            username=context["username"],
            mood=context["mood"],
            activity=context["activity"],
            location=context["location"],
            summary=context["summary"],
            text_content=context["text_content"],
            reaction_style=style_description,
            response_type=response_type
        )
    
    async def _generate_response(self, prompt: str) -> str:
        """Generate a response using OpenAI GPT."""
        try:
            response = await self.client.chat.completions.create(
                model=openai_config.text_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that generates natural, friend-like responses to social media content."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=100,  # Keep responses short
                temperature=0.8,  # Add some creativity
                frequency_penalty=0.3,  # Reduce repetition
                presence_penalty=0.1
            )
            
            generated_text = response.choices[0].message.content.strip()
            
            # Clean up the response
            return self._clean_response(generated_text)
            
        except Exception as e:
            logger.error(f"OpenAI response generation failed: {e}")
            raise
    
    async def _generate_backup_responses(self, context: Dict[str, str], 
                                       reaction_style: str, response_type: str, count: int = 2) -> List[str]:
        """Generate backup response options."""
        backup_responses = []
        
        try:
            for i in range(count):
                # Slight variation in prompt for diversity
                varied_prompt = self._build_prompt(context, reaction_style, response_type)
                varied_prompt += f"\n\nVariation {i+1}: Generate a different but equally natural response:"
                
                response = await self._generate_response(varied_prompt)
                if response and response not in backup_responses:
                    backup_responses.append(response)
                    
        except Exception as e:
            logger.warning(f"Failed to generate backup responses: {e}")
        
        # Add some template-based backups if AI generation fails
        if len(backup_responses) < 2:
            template_backups = self._get_template_responses(context, reaction_style)
            backup_responses.extend(template_backups[:2-len(backup_responses)])
        
        return backup_responses
    
    def _clean_response(self, response: str) -> str:
        """Clean and validate the generated response."""
        # Remove quotes if the AI wrapped the response
        response = response.strip('"\'')
        
        # Remove any prefixes like "Response:" or "Comment:"
        prefixes = ["response:", "comment:", "reply:", "dm:", "message:"]
        for prefix in prefixes:
            if response.lower().startswith(prefix):
                response = response[len(prefix):].strip()
        
        # Ensure it's not too long
        if len(response) > 150:
            response = response[:147] + "..."
        
        # Basic validation
        if not response or len(response.strip()) < 3:
            raise ValueError("Generated response too short or empty")
        
        return response
    
    def _calculate_confidence(self, analysis: StoryAnalysis) -> float:
        """Calculate confidence score for the generated reaction."""
        base_confidence = 0.7
        
        # Increase confidence based on analysis quality
        if analysis.mood != "neutral":
            base_confidence += 0.1
        
        if analysis.activity:
            base_confidence += 0.05
            
        if analysis.summary and len(analysis.summary) > 20:
            base_confidence += 0.1
        
        # Factor in analysis confidence
        base_confidence *= analysis.confidence_score
        
        return min(0.95, base_confidence)
    
    def _generate_fallback_reaction(self, story_data: StoryData, response_type: str) -> ReactionResponse:
        """Generate a safe fallback reaction when AI generation fails."""
        fallback_responses = [
            "Nice! 😊",
            "Looks great!",
            "Love this!",
            "Amazing! ✨",
            f"Hey {story_data.username}! 👋"
        ]
        
        # Choose based on story type
        if story_data.text:
            if any(word in story_data.text.lower() for word in ["good", "great", "awesome", "love"]):
                chosen_response = "So happy for you! 😊"
            else:
                chosen_response = "Thanks for sharing! ❤️"
        else:
            chosen_response = fallback_responses[0]
        
        return ReactionResponse(
            text=chosen_response,
            confidence=0.3,  # Low confidence for fallbacks
            reaction_type=response_type
        )
    
    def _get_template_responses(self, context: Dict[str, str], reaction_style: str) -> List[str]:
        """Get template-based backup responses."""
        templates = {
            "supportive_positive": [
                f"So happy for you, {context['username']}! 😊",
                "This looks amazing! ✨",
                "Love seeing this! ❤️"
            ],
            "enthusiastic": [
                f"Yes {context['username']}! 🔥",
                "This is incredible! 🙌",
                "Living your best life! ✨"
            ],
            "caring_supportive": [
                f"Thinking of you {context['username']} ❤️",
                "Hope you're doing well! 💕",
                "Sending you love! 🤗"
            ],
            "casual_friendly": [
                f"Hey {context['username']}! 👋",
                "Nice! 😊", 
                "Cool story! 👍"
            ]
        }
        
        return templates.get(reaction_style, templates["casual_friendly"])
    
    async def generate_multiple_reactions(self, stories_data: Dict[str, List[StoryData]], 
                                        analyses: Dict[str, List[StoryAnalysis]]) -> Dict[str, List[ReactionResponse]]:
        """Generate reactions for multiple users' stories."""
        results = {}
        
        for username in stories_data.keys():
            if username not in analyses:
                continue
                
            user_stories = stories_data[username]
            user_analyses = analyses[username]
            
            user_reactions = []
            
            for i, (story, analysis) in enumerate(zip(user_stories, user_analyses)):
                try:
                    # Generate reaction for each story
                    reaction = await self.generate_reaction(story, analysis)
                    user_reactions.append(reaction)
                    
                    logger.info(f"Generated reaction {i+1} for {username}")
                    
                except Exception as e:
                    logger.error(f"Failed to generate reaction for {username} story {i+1}: {e}")
                    fallback = self._generate_fallback_reaction(story, "comment")
                    user_reactions.append(fallback)
            
            results[username] = user_reactions
        
        return results


# Example usage and testing
async def test_reply_generator():
    """Test the reply generator with mock data."""
    generator = ReplyGenerator()
    
    # Mock story data
    mock_story = StoryData(
        username="test_friend",
        text="Just finished an amazing workout at the gym! 💪",
        story_type="text"
    )
    
    # Mock analysis
    from src.services.analyzer import StoryAnalysis
    mock_analysis = StoryAnalysis()
    mock_analysis.mood = "excited"
    mock_analysis.activity = "working out"
    mock_analysis.location_context = "gym"
    mock_analysis.summary = "Friend excited about gym workout"
    mock_analysis.confidence_score = 0.9
    
    # Generate reaction
    reaction = await generator.generate_reaction(mock_story, mock_analysis)
    
    logger.info(f"Generated reaction: '{reaction.text}'")
    logger.info(f"Confidence: {reaction.confidence}")
    logger.info(f"Backup options: {reaction.backup_responses}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_reply_generator())
