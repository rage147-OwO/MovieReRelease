# AiMate - Instagram Story Auto-Responder

An AI-powered Instagram story auto-responder that scrapes stories, analyzes content using OpenAI Vision API, and automatically sends natural reactions.

## Features

- 🤖 AI-powered story analysis using OpenAI Vision API
- 📱 Automated Instagram story scraping with Playwright
- 💬 Natural, friend-like reaction generation
- 🚀 FastAPI-based web server
- 📊 Optional Redis queue for task management
- 🔒 Secure credential management

## Quick Start

1. **Clone and install dependencies:**
   ```bash
   git clone <your-repo>
   cd AiMate
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Setup environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Run the server:**
   ```bash
   python -m uvicorn src.main:app --reload
   ```

4. **Test endpoints:**
   - Health check: `GET http://localhost:8000/health`
   - Manual trigger: `POST http://localhost:8000/trigger`

## Project Structure

```
/src
  /api
    - webhook.py            # FastAPI endpoints
  /services
    - scraper.py            # Instagram story scraper
    - analyzer.py           # AI story analyzer
    - reply_generator.py    # GPT-based reaction generator
    - dm_sender.py          # Automated DM sender
  /utils
    - env.py                # Environment management
    - logger.py             # Logging setup
  main.py                   # FastAPI server

/config
  - openai_config.py        # OpenAI settings
  - scraper_config.py       # Scraper settings
```

## Configuration

### Environment Variables

- `INSTAGRAM_USERNAME`: Your Instagram username
- `INSTAGRAM_PASSWORD`: Your Instagram password
- `OPENAI_API_KEY`: OpenAI API key
- `TARGET_ACCOUNTS`: Comma-separated list of accounts to monitor
- `REDIS_URL`: Redis connection string (optional)

## Docker Deployment

```bash
docker-compose up -d
```

## API Endpoints

### GET /health
Health check endpoint

### POST /trigger
Manually trigger story analysis for all target accounts

```json
{
  "accounts": ["optional", "account", "list"]
}
```

## Security Notes

- Keep your `.env` file secure and never commit it
- Use strong Instagram credentials
- Consider using Instagram's official API when available
- Respect rate limits and Instagram's terms of service

## Development

1. Install development dependencies
2. Run tests: `pytest`
3. Format code: `black src/`
4. Lint: `flake8 src/`

## License

MIT License
