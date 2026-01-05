from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Path
from fastapi.responses import FileResponse
from app.models.schemas import SearchResponse, Track
from app.services.vk import vk_service
import os
import aiohttp
from urllib.parse import unquote

router = APIRouter(
    prefix="/music",
    tags=["🎵 Music"],
)

def remove_file(path: str):
    try:
        os.remove(path)
    except Exception as e:
        print(f"Error deleting file {path}: {e}")

@router.get("/search", response_model=SearchResponse)
async def search(q: str = Query(..., description="Search query (artist, song title, or both)", example="Макс Корж")):
    """
    🔍 **Search for music tracks in VK**
    
    Returns a list of tracks matching the search query with album covers and download links.
    
    **Parameters:**
    - `q`: Search query (artist name, song title, or combination)
    
    **Returns:**
    - List of tracks with metadata including:
        - Track ID (for downloading)
        - Title and Artist
        - Duration in seconds
        - Album cover URL (if available)
        - Download API endpoint
    
    **Example:**
    ```
    GET /api/music/search?q=Макс Корж
    ```
    """
    if not q:
        raise HTTPException(status_code=400, detail="Empty query")
    
    tracks = await vk_service.search_tracks(q, limit=20)
    return {"items": tracks}

@router.get("/download/{track_id}", 
    responses={
        200: {
            "description": "MP3 file",
            "content": {"audio/mpeg": {}}
        },
        404: {"description": "Track not found or restricted"},
        502: {"description": "Failed to download from VK servers"}
    })
async def download(
    track_id: str = Path(..., description="Track ID in format 'ownerId_trackId'", example="371745449_456392423"),
    background_tasks: BackgroundTasks = None
):
    """
    ⬇️ **Download MP3 file by Track ID**
    
    Downloads the audio file from VK servers and streams it to the client.
    The file is automatically deleted after sending.
    
    **Parameters:**
    - `track_id`: Unique track identifier (obtained from search results)
    
    **Returns:**
    - MP3 audio file with proper filename and metadata
    
    **Errors:**
    - `404`: Track not found or access restricted
    - `502`: VK servers unavailable or download failed
    
    **Example:**
    ```
    GET /api/music/download/371745449_456392423
    ```
    """
    song = await vk_service.get_audio_url(track_id)
    
    if not song or not song.url:
        raise HTTPException(status_code=404, detail="Track not found or restricted")
        
    filename = f"{song.artist} - {song.title}.mp3".replace("/", "-")
    downloads_dir = "downloads"
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir)
        
    file_path = f"{downloads_dir}/{track_id}.mp3"
    
    # Скачиваем файл (стримим с ВК)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(song.url) as resp:
                if resp.status != 200:
                     raise HTTPException(status_code=502, detail="Failed to download from VK servers")
                with open(file_path, 'wb') as f:
                    f.write(await resp.read())
    except Exception as e:
        print(f"DL Error: {e}")
        raise HTTPException(status_code=500, detail="Internal download error")
    
    background_tasks.add_task(remove_file, file_path)
    
    return FileResponse(
        path=file_path, 
        filename=unquote(filename),
        media_type='audio/mpeg'
    )
    
@router.get("/recommendations", response_model=SearchResponse)
async def recommendations(
    track_id: str = Query(None, description="Track ID to base recommendations on", example="371745449_456392423"),
    query: str = Query(None, description="Search query for recommendations", example="Макс Корж"),
    limit: int = Query(20, description="Maximum number of recommendations", ge=1, le=50)
):
    """
    🎯 **Get personalized music recommendations**
    
    Returns recommended tracks based on:
    - A specific track (via `track_id`)
    - A search query (via `query`)
    - Popular tracks (if neither is provided)
    
    **Parameters:**
    - `track_id` (optional): Get recommendations similar to this track
    - `query` (optional): Search for recommendations matching this query
    - `limit`: Number of tracks to return (1-50, default: 20)
    
    **Returns:**
    - List of recommended tracks with full metadata
    
    **Examples:**
    ```
    GET /api/music/recommendations?track_id=371745449_456392423
    GET /api/music/recommendations?query=Макс Корж&limit=10
    GET /api/music/recommendations (returns popular tracks)
    ```
    """
    if query:
        tracks = await vk_service.search_tracks(query, limit)
    elif track_id:
        # Находим артиста по ID трека и ищем его песни
        song = await vk_service.get_audio_url(track_id)
        if song:
            tracks = await vk_service.search_tracks(song.artist, limit)
            # Убираем сам трек из выдачи
            tracks = [t for t in tracks if t['id'] != track_id]
        else:
            tracks = []
    else:
        # Fallback на популярное если ничего не задано
        tracks = await vk_service.search_tracks("Top 100", limit)
        
    return {"items": tracks}
