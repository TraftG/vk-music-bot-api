import os
import re
import asyncio
import hmac
import hashlib
import json
import aiohttp
from urllib.parse import parse_qsl, unquote
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from vkpymusic import Service

# Конфигурация
BOT_TOKEN = '8272982458:AAHRCpLrK9fln24FRGZk8T8WqSaXgptylIk'
VK_TOKEN = 'vk1.a.vOwFUs6mJmbAdaXHYbovHuBuVmXwL2pv7Oa-FUHWjLl8uXPE-YRQaL8wAwdQiG-454DWiOsPOBPaH3TBwldR__3YDAgkYHkvRWsZgeW0vjAigUugaoXqVNNhZj_rbzjAz3OoG1KGwyiVxY9hPcNzsjNMlgOqlaaEy7Ux0dZDJbEWCav3CVzvLVUE8BGIz22fu78TWqBV6Jo37-o_o1cYcQ'

app = FastAPI()

# --- MONGODB SETUP ---
MONGO_URL = "mongodb://localhost:27017"
client = AsyncIOMotorClient(MONGO_URL)
db = client.music_bot_db
users_collection = db.users
history_collection = db.history

# --- VK SERVICE SETUP ---
# Пробуем универсальный Android агент для VK Admin токена
vks = Service('VKAndroidApp/5.52-4543', VK_TOKEN)

# --- UTILS ---

def remove_file(path: str):
    """Удаление файла после отправки."""
    try:
        os.remove(path)
    except Exception as e:
        print(f"Error deleting file {path}: {e}")

# --- API ENDPOINTS ---

@app.get("/")
async def root():
    return {"message": "Music Bot Backend (VK Edition) is running!"}

@app.get("/search")
async def search(q: str):
    """
    Поиск музыки в ВК через прямое API (для обложек).
    """
    if not q:
        raise HTTPException(status_code=400, detail="Empty query")
    
    try:
        # Прямой запрос к VK API, чтобы получить обложки
        async with aiohttp.ClientSession() as session:
            params = {
                'access_token': VK_TOKEN,
                'v': '5.131',
                'q': q,
                'count': 20,
                'sort': 2, # по популярности
                'auto_complete': 1
            }
            # Используем User-Agent от VK Admin на всякий случай
            headers = {
                'User-Agent': 'VKAndroidApp/5.52-4543'
            }
            async with session.get('https://api.vk.com/method/audio.search', params=params, headers=headers) as resp:
                data = await resp.json()
                
        if 'error' in data:
            print(f"VK API Error: {data['error']}")
            return JSONResponse(content=[], status_code=500)
            
        items = data.get('response', {}).get('items', [])
        response = []
        
        for item in items:
            # item - это полный JSON трека
            # Если нет URL, пропускаем (хотя в прямом API url может быть в другом месте или скрыт)
            if not item.get('url'):
                 print(f"No URL for {item.get('artist')} - {item.get('title')}")
                 # Иногда url скрыт, но мы можем потом его получить через getById. 
                 # Но пока добавим в выдачу, скачивание через getById сработает
            
            # Ищем обложку
            cover_url = None
            album = item.get('album', {})
            thumb = album.get('thumb', {})
            if thumb:
                # Берем самую большую
                cover_url = thumb.get('photo_600') or thumb.get('photo_300') or thumb.get('photo_68')
            
            track_id_full = f"{item['owner_id']}_{item['id']}"
            
            response.append({
                "id": track_id_full,
                "title": item.get('title'),
                "artist": item.get('artist'),
                "duration": item.get('duration'),
                "cover_url": cover_url,
                "url_api": f"/download/{track_id_full}" 
            })
            
            if len(response) >= 10:
                break
        
        return JSONResponse(content=response)

    except Exception as e:
        print(f"Search error: {e}")
        return JSONResponse(content=[], status_code=500)

@app.get("/download/{track_id}")
async def download(track_id: str, background_tasks: BackgroundTasks):
    """
    Скачивание трека по ID (owner_id_track_id).
    """
    try:
        # 1. Получаем свежую информацию о треке (чтобы получить актуальный URL)
        # В vkpymusic метод принимает список ID
        songs = await asyncio.to_thread(vks.get_songs_by_id, [track_id])
        
        if not songs:
            raise HTTPException(status_code=404, detail="Track not found")
            
        song = songs[0]
        mp3_url = song.url
        
        if not mp3_url:
            raise HTTPException(status_code=403, detail="No direct URL (track restricted)")
            
        # 2. Скачиваем файл во временную папку
        filename = f"{song.artist} - {song.title}.mp3".replace("/", "-") # Чистим слеши
        file_path = f"downloads/{track_id}.mp3"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(mp3_url) as resp:
                if resp.status != 200:
                     raise HTTPException(status_code=502, detail="Failed to download from VK servers")
                with open(file_path, 'wb') as f:
                    f.write(await resp.read())
        
        # 3. Отдаем файл и планируем удаление
        background_tasks.add_task(remove_file, file_path)
        
        # Кодируем имя файла для заголовка Content-Disposition (чтобы кириллица не ломалась)
        encoded_filename = unquote(filename)
        
        return FileResponse(
            path=file_path, 
            filename=encoded_filename,
            media_type='audio/mpeg'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/recommendations")
async def recommendations(track_id: str = None, query: str = None, limit: int = 5):
    """
    Рекомендации.
    Можно искать похожие по track_id (если поддерживается) или просто новый поиск.
    ВК API не дает прямых рекомендаций по ID песни публично, 
    поэтому используем поиск похожих по артисту/названию или 'get_popular' если ничего нет.
    """
    try:
        songs = []
        if query:
            # Ищем что-то похожее на запрос (mix)
             songs = await asyncio.to_thread(vks.search_songs_by_text, query, limit)
        elif track_id:
            # Получим инфу о треке и найдем песни того же исполнителя
            info = await asyncio.to_thread(vks.get_songs_by_id, [track_id])
            if info:
                artist = info[0].artist
                # Ищем этого артиста
                songs = await asyncio.to_thread(vks.search_songs_by_text, artist, limit)
                # Фильтруем сам исходный трек
                songs = [s for s in songs if f"{s.owner_id}_{s.track_id}" != track_id]
        else:
            # Если ничего не задано, вернем популярное
            songs = await asyncio.to_thread(vks.get_popular, limit)

        response = []
        for song in songs[:limit]:
            tid = f"{song.owner_id}_{song.track_id}"
            response.append({
                "id": tid,
                "title": song.title,
                "artist": song.artist,
                "duration": song.duration
            })
            
        return JSONResponse(content=response)
        
    except Exception as e:
        print(f"Recs error: {e}")
        return JSONResponse(content=[], status_code=500)

# --- AUTH LOGIC ---

class InitDataRequest(BaseModel):
    initData: str
def validate_init_data(init_data: str, token: str):
    """
    Валидация данных от Telegram WebApp.
    """
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

@app.post("/auth")
async def auth(request: InitDataRequest):
    """
    Авторизация через MongoDB.
    """
    try:
        user_info = validate_init_data(request.initData, BOT_TOKEN)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    user_id = user_info.get("id")
    
    # Обновляем данные пользователя (upsert)
    user_doc = {
        "id": user_id,
        "first_name": user_info.get("first_name", ""),
        "username": user_info.get("username", ""),
        "language_code": user_info.get("language_code", "en"),
        "photo_url": user_info.get("photo_url", ""),
        "last_login": datetime.utcnow()
    }
    
    await users_collection.update_one(
        {"id": user_id},
        {"$set": user_doc},
        upsert=True
    )
        
    return {
        "status": "ok",
        "user": user_info
    }

class HistoryItem(BaseModel):
    user_id: int
    track_id: str
    title: str
    artist: str = "Unknown"

@app.post("/history")
async def add_history(item: HistoryItem):
    """
    Сохраняет прослушанный трек в историю.
    """
    doc = item.dict()
    doc['listened_at'] = datetime.utcnow()
    await history_collection.insert_one(doc)
    return {"status": "saved"}

# Создаем папку для скачивания, если нет
if not os.path.exists("downloads"):
    os.makedirs("downloads")

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'quiet': True,
}

def clean_title(title):
    """Очищает название от мусора."""
    # 1. Заменяем "Official Video" и подобные без скобок (бывает и такое)
    title = re.sub(r'(?i)\b(official|music|lyric|lyrics)\s+(video|audio)\b', '', title)
    
    # 2. Удаляем содержимое скобок, ЕСЛИ там есть мусорные слова
    # Функция-замена, которая проверяет содержимое скобок
    def clean_brackets(match):
        content = match.group(0) # Всё выражение в скобках, например (feat. Trippie Redd)
        # Если внутри есть стоп-слова - удаляем всё содержимое
        if re.search(r'(?i)(official|video|audio|lyrics|lyric|hq|hd|4k|mv|music video|clip)', content):
            return ""
        return content

    # Применяем ко всем круглым и квадратным скобкам
    title = re.sub(r'\([^\)]+\)', clean_brackets, title)
    title = re.sub(r'\[[^\]]+\]', clean_brackets, title)
    
    # 3. Удаляем хештеги
    title = re.sub(r'#\S+', '', title)

    # 4. Финальная зачистка: лишние пробелы и знаки препинания в конце
    title = " ".join(title.split())
    # Удаляем пустые скобки, если остались "()", "[]"
    title = title.replace("()", "").replace("[]", "")
    
    return title.strip()

def search_yt_logic(query):
    """Поиск на YouTube через yt-dlp."""
    opts = {'quiet': True, 'extract_flat': True, 'noplaylist': True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            return info['entries']
        except Exception as e:
            print(f"Error search: {e}")
            return []

def download_track(url):
    """Скачивание трека."""
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=True)
        base_path = ydl.prepare_filename(info)
        filename = os.path.splitext(base_path)[0] + ".mp3"
        return {
            'path': filename,
            'title': clean_title(info.get('title', 'Unknown')),
            'artist': info.get('uploader', 'Unknown')
        }

def remove_file(path: str):
    """Удаление файла после отправки."""
    try:
        os.remove(path)
    except Exception as e:
        print(f"Error deleting file {path}: {e}")

@app.get("/")
async def root():
    return {"message": "Music Bot Backend is running!"}

@app.get("/search")
async def search(q: str):
    """Эндпоинт для поиска музыки."""
    if not q:
        raise HTTPException(status_code=400, detail="Empty query")
    
    results = await asyncio.to_thread(search_yt_logic, q)
    
    response = []
    for track in results:
        response.append({
            "id": track['id'],
            "title": clean_title(track['title']),
            "original_title": track['title'],
            "url": f"https://www.youtube.com/watch?v={track['id']}"
        })
    
    return JSONResponse(content=response)

@app.get("/recommendations")
async def recommendations(video_id: str, limit: int = 5):
    """
    Эндпоинт для рекомендаций.
    Ищет похожие треки на основе переданного video_id.
    """
    if not video_id:
        raise HTTPException(status_code=400, detail="Video ID is required")
        
    try:
        # 1. Получаем инфу о базовом треке
        # Используем 'extract_flat': True чтобы быстро получить метаданные без полной загрузки
        opts_info = {'quiet': True, 'extract_flat': True}
        seed_info = await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(opts_info).extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False))
        
        if not seed_info:
             raise HTTPException(status_code=404, detail="Video not found")

        seed_title = clean_title(seed_info.get('title', ''))
        seed_artist = seed_info.get('uploader', '')
        
        # 2. Формируем запрос для поиска похожих
        # Хороший паттерн: "{Artist} {Title} mix" или "Songs like {Title}"
        # Попробуем найти микс или просто похожие видео
        query = f"{seed_artist} {seed_title} playlist mix"
        
        # Ищем чуть больше, чтобы отфильтровать дубликаты
        search_limit = limit + 5
        opts_search = {'quiet': True, 'extract_flat': True, 'noplaylist': True}
        
        results = await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(opts_search).extract_info(f"ytsearch{search_limit}:{query}", download=False))
        
        response = []
        seen_ids = {video_id} # Исключаем сам seed трек
        
        if 'entries' in results:
            for track in results['entries']:
                if len(response) >= limit:
                    break
                    
                tid = track['id']
                if tid in seen_ids:
                    continue
                
                # Фильтруем слишком длинные видео (миксы по часу), если это не музыка
                # Но flat_extract не всегда дает duration. Пропустим пока.
                
                clean = clean_title(track['title'])
                
                response.append({
                    "id": tid,
                    "title": clean,
                    "original_title": track['title'],
                    "url": f"https://www.youtube.com/watch?v={tid}"
                })
                seen_ids.add(tid)
                
        return JSONResponse(content=response)

    except Exception as e:
        print(f"Error recommendations: {e}")
        # Если не получилось найти рекомендации, вернем пустой список, а не 500
        return JSONResponse(content=[])

@app.get("/download/{video_id}")
async def download(video_id: str, background_tasks: BackgroundTasks):
    """Эндпоинт для скачивания и отдачи файла."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        file_info = await asyncio.to_thread(download_track, url)
        file_path = file_info['path']
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=500, detail="File download failed")
        
        # Кодируем имя файла для заголовка Content-Disposition
        # encode uri component analogue might be needed/good practice but simple for now
        filename = f"{file_info['artist']} - {file_info['title']}.mp3"
        
        # Планируем удаление файла после отправки
        background_tasks.add_task(remove_file, file_path)
        
        return FileResponse(
            path=file_path, 
            filename=filename,
            media_type='audio/mpeg'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
