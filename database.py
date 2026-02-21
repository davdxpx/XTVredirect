from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConfigurationError
from config import Config
from datetime import datetime
from utils.logger import setup_logger

logger = setup_logger(__name__)

class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(Config.REDIRECT_DB_URI)
        try:
            self.db = self.client.get_default_database()
        except ConfigurationError:
            logger.warning("No default database name provided in URI. Using 'xtv_redirect'.")
            self.db = self.client.get_database("xtv_redirect")

        self.redirects = self.db.redirect_links
        logger.info("Connected to MongoDB")

    async def create_redirect(self, data: dict):
        """
        Creates a new redirect entry.
        data should contain: code, series_name, tmdb_id, private_channel_id, invite_link
        """
        data['created_at'] = datetime.utcnow()
        data['used_count'] = 0
        data['last_used'] = None

        try:
            result = await self.redirects.insert_one(data)
            logger.info(f"Created redirect for {data.get('series_name')} with code {data.get('code')}")
            return result.inserted_id
        except Exception as e:
            logger.error(f"Error creating redirect: {e}")
            return None

    async def get_redirect(self, code: str):
        """Retrieves a redirect entry by code."""
        return await self.redirects.find_one({"code": code})

    async def update_stats(self, code: str):
        """Updates used_count and last_used for a redirect."""
        await self.redirects.update_one(
            {"code": code},
            {
                "$inc": {"used_count": 1},
                "$set": {"last_used": datetime.utcnow()}
            }
        )

    async def get_all_redirects(self):
        """Retrieves all redirect entries."""
        cursor = self.redirects.find().sort("created_at", -1)
        return await cursor.to_list(length=None)

    async def count_redirects(self):
        return await self.redirects.count_documents({})

# Global instance
db = Database()
