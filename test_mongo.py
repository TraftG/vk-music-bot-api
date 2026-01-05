import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime

async def test_mongo():
    # Строка подключения
    MONGO_URL = "mongodb://localhost:27017"
    client = AsyncIOMotorClient(MONGO_URL)
    
    # База и коллекция
    db = client.music_bot_db
    users = db.users
    
    # Тестовые данные
    test_user = {
        "id": 123456789,
        "first_name": "Test User",
        "username": "test_bot_user",
        "language_code": "ru",
        "last_login": datetime.utcnow()
    }
    
    print("⏳ Пытаюсь записать данные в MongoDB...")
    
    try:
        result = await users.update_one(
            {"id": test_user["id"]},
            {"$set": test_user},
            upsert=True
        )
        print("✅ Запись успешна!")
        print(f"Matched count: {result.matched_count}")
        print(f"Modified count: {result.modified_count}")
        print(f"Upserted id: {result.upserted_id}")
        
        # Проверяем чтение
        user_from_db = await users.find_one({"id": 123456789})
        print(f"📄 Прочитано из БД: {user_from_db}")
        
    except Exception as e:
        print(f"❌ Ошибка подключения или записи: {e}")

if __name__ == "__main__":
    asyncio.run(test_mongo())
