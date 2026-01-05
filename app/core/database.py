from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

class Database:
    client: AsyncIOMotorClient = None
    music_db = None

db = Database()

async def connect_to_mongo():
    db.client = AsyncIOMotorClient(settings.mongo_url)
    db.music_db = db.client[settings.db_name]
    print("✅ Connected to MongoDB")

async def close_mongo_connection():
    db.client.close()
    print("❌ Closed MongoDB connection")
