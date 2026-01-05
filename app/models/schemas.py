from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional

# --- AUTH ---
class InitDataRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "initData": "query_id=AAHdF6IQAAAAAN0XohDhrOrc&user=%7B%22id%22%3A279058397%2C%22first_name%22%3A%22Вадим%22%2C%22last_name%22%3A%22%22%2C%22username%22%3A%22vdkfrost%22%2C%22language_code%22%3A%22ru%22%7D&auth_date=1662771648&hash=c501b71e775f74ce10e377dea85a7ea24ecd640b223ea86dfe453e0eaed2e2b2"
            }
        }
    )
    
    initData: str = Field(..., description="Query string from window.Telegram.WebApp.initData")

class User(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 123456789,
                "first_name": "Иван",
                "username": "ivan_music",
                "language_code": "ru",
                "photo_url": "https://t.me/i/userpic/320/example.jpg"
            }
        }
    )
    
    id: int
    first_name: str
    username: Optional[str] = None
    language_code: Optional[str] = None
    photo_url: Optional[str] = None

class AuthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "user": {
                    "id": 123456789,
                    "first_name": "Иван",
                    "username": "ivan_music",
                    "language_code": "ru"
                }
            }
        }
    )
    
    status: str
    user: User

# --- MUSIC ---
class Track(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "371745449_456392423",
                "title": "Жить в кайф",
                "artist": "Макс Корж",
                "duration": 234,
                "cover_url": "https://sun9-12.userapi.com/impg/c857136/v857136449/1234/photo.jpg",
                "url_api": "/api/music/download/371745449_456392423"
            }
        }
    )
    
    id: str = Field(..., description="Unique track ID (ownerId_trackId)")
    title: str
    artist: str
    duration: int
    cover_url: Optional[str] = Field(None, description="URL of the album cover")
    url_api: str = Field(..., description="Internal API URL to download the MP3")

class SearchResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": "371745449_456392423",
                        "title": "Жить в кайф",
                        "artist": "Макс Корж",
                        "duration": 234,
                        "cover_url": "https://sun9-12.userapi.com/impg/c857136/v857136449/1234/photo.jpg",
                        "url_api": "/api/music/download/371745449_456392423"
                    },
                    {
                        "id": "474499231_456695516",
                        "title": "Толпы",
                        "artist": "madk1d",
                        "duration": 90,
                        "cover_url": "https://sun9-12.userapi.com/impg/c857136/v857136231/5678/photo.jpg",
                        "url_api": "/api/music/download/474499231_456695516"
                    }
                ]
            }
        }
    )
    
    items: List[Track]

class HistoryItem(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 123456789,
                "track_id": "371745449_456392423",
                "title": "Жить в кайф",
                "artist": "Макс Корж"
            }
        }
    )
    
    user_id: int
    track_id: str
    title: str
    artist: str = "Unknown"

class StatusResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "saved"
            }
        }
    )
    
    status: str
