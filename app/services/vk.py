import asyncio
import aiohttp
from vkpymusic import Service
from app.core.config import settings

class VKService:
    def __init__(self):
        # Инициализируем библиотеку vkpymusic. 
        # Используем наш "волшебный" User-Agent и Токен.
        self.service = Service(settings.vk_user_agent, settings.vk_token)

    async def search_tracks(self, query: str, limit: int = 20):
        """
        Прямой поиск через API для получения обложек.
        """
        async with aiohttp.ClientSession() as session:
            params = {
                'access_token': settings.vk_token,
                'v': '5.131',
                'q': query,
                'count': limit,
                'sort': 2, 
                'auto_complete': 1
            }
            # Честно прикидываемся официальным клиентом
            headers = {
                'User-Agent': settings.vk_user_agent
            }
            
            try:
                async with session.get('https://api.vk.com/method/audio.search', params=params, headers=headers) as resp:
                    data = await resp.json()
            except Exception as e:
                print(f"VK API Connection Error: {e}")
                return []

        if 'error' in data:
            print(f"VK API Error: {data['error']}")
            return []

        items = data.get('response', {}).get('items', [])
        tracks = []
        
        for item in items:
            # Не пропускаем треки без URL в поиске, так как мы получим его в /download
            # if not item.get('url'):
            #    continue

            # Извлекаем обложку
            cover_url = None
            album = item.get('album', {})
            thumb = album.get('thumb', {}) if album else {}
            if thumb:
                cover_url = thumb.get('photo_600') or thumb.get('photo_300') or thumb.get('photo_68')

            track_id = f"{item['owner_id']}_{item['id']}"
            
            tracks.append({
                "id": track_id,
                "title": item.get('title'),
                "artist": item.get('artist'),
                "duration": item.get('duration'),
                "cover_url": cover_url,
                "url_api": f"/api/music/download/{track_id}"
            })
            
        print(f"✅ Found {len(tracks)} tracks for query: {query}")
        return tracks

    async def get_audio_url(self, track_id: str):
        """
        Получение ссылки на MP3 через vkpymusic (она умеет делать getById).
        """
        # vkpymusic принимает список ID
        songs = await asyncio.to_thread(self.service.get_songs_by_id, [track_id])
        if not songs:
            return None
        return songs[0]

vk_service = VKService()
