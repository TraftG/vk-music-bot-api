from fastapi import APIRouter, HTTPException, Body
from app.models.schemas import InitDataRequest, AuthResponse, HistoryItem, StatusResponse
from app.core.config import settings
from app.core.database import db
from datetime import datetime
import hmac
import hashlib
import json
from urllib.parse import parse_qsl

router = APIRouter(
    prefix="/auth",
    tags=["🔐 Authentication & User"],
    responses={404: {"description": "Not found"}},
)

def validate_init_data(init_data: str, token: str):
    try:
        parsed_data = dict(parse_qsl(init_data))
    except ValueError:
         raise ValueError("Invalid initData format")

    if "hash" not in parsed_data:
        raise ValueError("Hash is missing")

    hash_check = parsed_data.pop("hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if calculated_hash != hash_check:
        raise ValueError("Invalid hash signature")
        
    user_data_json = parsed_data.get("user")
    if not user_data_json:
        raise ValueError("User data missing")
        
    return json.loads(user_data_json)

@router.post("/login", response_model=AuthResponse)
async def login(request: InitDataRequest):
    """
    🔐 **Authenticate user via Telegram Mini App**
    
    Validates the `initData` string from Telegram WebApp and registers/updates the user in the database.
    
    **Security:**
    - Uses HMAC-SHA256 signature verification
    - Validates against bot token
    - Prevents tampering with user data
    
    **Parameters:**
    - `initData`: Raw query string from `window.Telegram.WebApp.initData`
    
    **Returns:**
    - User information and authentication status
    
    **Errors:**
    - `401 Unauthorized`: Invalid signature or missing hash
    
    **Example Request:**
    ```json
    {
        "initData": "query_id=AAHdF6IQ...&user=%7B%22id%22%3A123...&hash=c501b71e..."
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "user": {
            "id": 123456789,
            "first_name": "Иван",
            "username": "ivan_music",
            "language_code": "ru"
        }
    }
    ```
    """
    try:
        user_info = validate_init_data(request.initData, settings.bot_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    user_id = user_info.get("id")
    
    user_doc = {
        "id": user_id,
        "first_name": user_info.get("first_name", ""),
        "username": user_info.get("username", ""),
        "language_code": user_info.get("language_code", "en"),
        "photo_url": user_info.get("photo_url", ""),
        "last_login": datetime.utcnow()
    }
    
    # Используем коллекцию из db.music_db
    collection = db.music_db.users
    await collection.update_one(
        {"id": user_id},
        {"$set": user_doc},
        upsert=True
    )
        
    return {
        "status": "ok",
        "user": user_info
    }

@router.post("/history", response_model=StatusResponse)
async def add_history(item: HistoryItem):
    """
    📊 **Add track to user listening history**
    
    Records when a user listens to a track for analytics and personalized recommendations.
    
    **Parameters:**
    - `user_id`: Telegram user ID
    - `track_id`: VK track identifier
    - `title`: Track title
    - `artist`: Artist name
    
    **Returns:**
    - Confirmation status
    
    **Example Request:**
    ```json
    {
        "user_id": 123456789,
        "track_id": "371745449_456392423",
        "title": "Жить в кайф",
        "artist": "Макс Корж"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "saved"
    }
    ```
    """
    collection = db.music_db.history
    doc = item.dict()
    doc['listened_at'] = datetime.utcnow()
    await collection.insert_one(doc)
    return {"status": "saved"}
