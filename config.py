import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    REDIRECT_DB_URI = os.getenv("REDIRECT_DB_URI")
    CEO_ID = int(os.getenv("CEO_ID", 0))
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @staticmethod
    def validate():
        missing = []
        if not Config.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not Config.REDIRECT_DB_URI:
            missing.append("REDIRECT_DB_URI")
        if not Config.CEO_ID:
            missing.append("CEO_ID")
        if not Config.TMDB_API_KEY:
            missing.append("TMDB_API_KEY")

        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")
