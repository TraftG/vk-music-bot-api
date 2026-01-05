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
    token = token.strip()
    from urllib.parse import parse_qsl, unquote
    
    # 1. Собираем параметры
    params = dict(parse_qsl(init_data))
    if "hash" not in params:
        raise ValueError("Hash is missing")
    
    received_hash = params.pop("hash")
    params.pop("signature", None) # Удаляем signature (Bot API 7.0+)

    # 2. Подготовка разных вариантов Data Check String
    variants = []
    
    # Вариант А: Все поля, сортировка по алфавиту (Стандарт)
    raw_sorted = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    variants.append(raw_sorted)
    
    # Вариант Б: Исправляем экранирование слешей в поле user
    if "user" in params:
        user_fixed = params["user"].replace("\\/", "/")
        params_fixed = params.copy()
        params_fixed["user"] = user_fixed
        variants.append("\n".join(f"{k}={v}" for k, v in sorted(params_fixed.items())))

    # Вариант В: Только базовые поля (иногда доп. поля мешают)
    core_keys = ["user", "auth_date", "query_id"]
    core_params = {k: v for k, v in params.items() if k in core_keys}
    if core_params:
        variants.append("\n".join(f"{k}={v}" for k, v in sorted(core_params.items())))

    # 3. Подготовка вариантов секретного ключа
    keys = []
    # Стандарт Mini App
    keys.append(hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest())
    # Вариант для Widgets (на всякий случай)
    keys.append(hashlib.sha256(token.encode()).digest())

    # 4. Перебор всех комбинаций
    for key in keys:
        for check_str in variants:
            calc_hash = hmac.new(key, check_str.encode(), hashlib.sha256).hexdigest()
            if calc_hash.lower() == received_hash.lower():
                print(f"✅ Auth Success with variant!")
                return json.loads(params["user"])

    # Если ничего не подошло - выводим финальный дебаг
    print(f"--- AUTH FAILURE DEBUG ---")
    print(f"Check String (Variant A):\n{raw_sorted}")
    print(f"Calculated: {hmac.new(keys[0], raw_sorted.encode(), hashlib.sha256).hexdigest()}")
    print(f"Expected:   {received_hash}")
    print(f"--------------------------")
    raise ValueError("Invalid hash signature")

@router.post("/login", response_model=AuthResponse)
async def login(request: InitDataRequest):
    """
    🔐 **Authenticate user via Telegram Mini App**
    """
    # --- DEBUG BYPASS ДЛЯ РАЗРАБОТКИ ---
    # Если в .env включен DEBUG=true, можно войти просто отправив "debug:ID"
    if settings.debug and request.initData.startswith("debug:"):
        user_id = int(request.initData.split(":")[1])
        print(f"⚠️ DEBUG LOGIN: User ID {user_id}")
        mock_user = {
            "id": user_id,
            "first_name": "Developer",
            "username": f"dev_{user_id}",
            "language_code": "ru"
        }
        return {"status": "ok", "user": mock_user}

    try:
        user_info = validate_init_data(request.initData, settings.bot_token)
    except ValueError as e:
        print(f"❌ Auth Failed: {e}")
        # Если не получается войти, попробуйте отправить в initData строку: debug:6750739892
        raise HTTPException(status_code=401, detail=str(e))
    
    user_id = user_info.get("id")
    print(f"✅ User Login Success: {user_info.get('first_name')} (ID: {user_id})")
    
    user_doc = {
        "id": user_id,
        "first_name": user_info.get("first_name", ""),
        "username": user_info.get("username", ""),
        "language_code": user_info.get("language_code", "en"),
        "photo_url": user_info.get("photo_url", ""),
        "last_login": datetime.utcnow()
    }
    
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
