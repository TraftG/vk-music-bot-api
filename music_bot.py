import asyncio
import os
import yt_dlp
import vk_api
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# --- НАСТРОЙКИ ---
TOKEN = '8272982458:AAHRCpLrK9fln24FRGZk8T8WqSaXgptylIk'
VK_TOKEN = 'vk1.a.mIheQn4pWOwULgL4Qbe1lyX3YFExcZwZSdl79Xx8j4XYNaRFWkqewK0oavX4j0FcKRGnaGMAiLVQgQFFzncBdb1pB2iUVuMUEcfCmrrFn6RhoOzWxj_pevgD1-Xg_9NArmiezMrMDb29mtTxGhT_xpkqIXfcb7r5vdwnHtSY6F-BA41KsJpuvsEe5Jae_oNUDYYCBQicAD6capwEFua52Q'
COOKIES_FILE = 'cookies.txt' 
bot = Bot(token=TOKEN)
dp = Dispatcher()

vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'cookiefile': COOKIES_FILE,
    'noplaylist': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'quiet': True,
}

# 1. Поиск через прямое API ВК
def search_vk_api(query):
    try:
        # Увеличим count до 10, чтобы было из чего выбирать, если первые результаты — мусор
        results = vk.audio.search(q=query, count=10, v='5.131')
        if not results or 'items' not in results:
            return []
        
        tracks = []
        for item in results['items']:
            title = item.get('title', '')
            artist = item.get('artist', '')

            # ФИЛЬТР: Пропускаем результаты, содержащие слова "официальном", "приложении", "ВКонтакте"
            # Обычно мусорные сообщения содержат эти фразы
            garbage_words = ["официальном", "приложении", "вконтакте", "аудио доступно"]
            is_garbage = any(word in title.lower() or word in artist.lower() for word in garbage_words)

            if not is_garbage and artist and title:
                tracks.append({
                    'id': f"{item['owner_id']}_{item['id']}",
                    'title': title,
                    'artist': artist
                })
            
            # Нам нужно только 5 реальных песен
            if len(tracks) >= 5:
                break
                
        return tracks
    except Exception as e:
        print(f"Ошибка API ВК: {e}")
        return []
@dp.message(F.text & ~F.text.startswith('/'))
async def handle_message(message: types.Message):
    wait_msg = await message.answer("🔎 Ищу в VK Музыке...")
    
    results = await asyncio.to_thread(search_vk_api, message.text)
    
    if not results:
        await wait_msg.edit_text("Ничего не найдено. Проверь настройки приватности аудио в ВК (должны быть открыты для всех).")
        return

    keyboard = []
    for track in results:
        # Формируем кнопку. В callback_data передаем ID
        btn_text = f"🎵 {track['artist']} - {track['title']}"[:50]
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"vk_{track['id']}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await wait_msg.edit_text(f"Результаты по запросу '{message.text}':", reply_markup=markup)

# 2. Скачивание через yt-dlp по ссылке ВК
@dp.callback_query(F.data.startswith("vk_"))
async def download_callback(callback: CallbackQuery):
    track_id = callback.data.split("_")[1]
    url = f"https://vk.com/audio{track_id}"
    
    await callback.message.edit_text("📥 Загружаю MP3...")

    try:
        file_info = await asyncio.to_thread(download_track, url)
        
        await callback.message.answer_audio(
            audio=types.FSInputFile(file_info['path']),
            title=file_info['title'],
            performer=file_info['artist']
        )
        
        await callback.message.delete()
        if os.path.exists(file_info['path']):
            os.remove(file_info['path'])
            
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка скачивания: {e}\nПопробуй обновить cookies.txt")
    
    await callback.answer()

def download_track(url):
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=True)
        # Находим путь к итоговому файлу
        base_path = ydl.prepare_filename(info)
        filename = os.path.splitext(base_path)[0] + ".mp3"
        
        return {
            'path': filename,
            'title': info.get('title', 'Unknown'),
            'artist': info.get('uploader', 'VK Artist')
        }

async def main():
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    print("Бот ВК запущен!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())