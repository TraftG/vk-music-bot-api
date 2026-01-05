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
    token = token.strip().strip("'\"") # Очищаем от пробелов и кавычек
    from urllib.parse import parse_qsl, unquote
    import hashlib
    import hmac
    import json

    # 1. Собираем все параметры
    params = dict(parse_qsl(init_data))
    if "hash" not in params:
        raise ValueError("Hash is missing")
    
    received_hash = params.pop("hash")
    params.pop("signature", None) # Telegram v7.0+

    # 2. Подготовка вариантов секретных ключей
    keys = [
        hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest(), # Стандарт
        hashlib.sha256(token.encode()).digest() # Альтернативный (для виджетов)
    ]

    # 3. Подготовка вариантов наборов полей
    # Вариант А: Все что пришло (отсортировано)
    full_sorted = sorted(params.items())
    
    # Вариант Б: Только базовые (user, auth_date, query_id)
    core_keys = ["user", "auth_date", "query_id"]
    core_sorted = sorted([(k, v) for k, v in params.items() if k in core_keys])

    field_sets = [full_sorted, core_sorted]

    # 4. Перебор всех комбинаций
    for key in keys:
        for fields in field_sets:
            if not fields: continue
            
            # Пробуем два вида строки: как есть и с исправленными слешами в user
            combinations = []
            
            # Подвариант 1: Как пришло
            combinations.append("\n".join(f"{k}={v}" for k, v in fields))
            
            # Подвариант 2: С исправлением слешей (если есть user)
            has_user = False
            fields_fixed = []
            for k, v in fields:
                if k == "user" and "\\/" in v:
                    has_user = True
                    fields_fixed.append((k, v.replace("\\/", "/")))
                else:
                    fields_fixed.append((k, v))
            if has_user:
                combinations.append("\n".join(f"{k}={v}" for k, v in fields_fixed))

            for check_str in combinations:
                calc_hash = hmac.new(key, check_str.encode(), hashlib.sha256).hexdigest()
                if calc_hash.lower() == received_hash.lower():
                    print(f"✅ Auth SUCCESS! Variant matched.")
                    # Возвращаем данные пользователя
                    user_val = next((v for k, v in fields if k == "user"), None)
                    return json.loads(user_val)

    # Если ничего не помогло - выводим финальный дебаг для отладки
    raw_sorted_str = "\n".join(f"{k}={v}" for k, v in full_sorted)
    print(f"--- FATAL AUTH FAILURE ---")
    print(f"Final Check String Attempted:\n{raw_sorted_str}")
    print(f"Expected Hash: {received_hash}")
    print(f"Calculated (Std): {hmac.new(keys[0], raw_sorted_str.encode(), hashlib.sha256).hexdigest()}")
    print(f"--------------------------")
    raise ValueError("Invalid hash signature")

@router.post("/login", response_model=AuthResponse)
async def login(request: InitDataRequest):
    """
    🔐 **Authenticate user via Telegram Mini App**
    """
    # --- DEBUG BYPASS ---
    if settings.debug and request.initData.startswith("debug:"):
        user_id = int(request.initData.split(":")[1])
        user_info = {
            "id": user_id, 
            "first_name": "Developer", 
            "username": f"dev_{user_id}",
            "language_code": "ru",
            "photo_url": ""
        }
        # Регистрируем в базе даже через дебаг
        user_doc = {**user_info, "last_login": datetime.utcnow()}
        await db.music_db.users.update_one({"id": user_id}, {"$set": user_doc}, upsert=True)
        return {"status": "ok", "user": user_info}

    try:
        user_info = validate_init_data(request.initData, settings.bot_token)
    except Exception as e:
        print(f"❌ Auth Error: {e}")
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
    
    await db.music_db.users.update_one(
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
