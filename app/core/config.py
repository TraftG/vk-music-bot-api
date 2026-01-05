from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Telegram Bot
    bot_token: str
    
    # VK API
    vk_token: str
    vk_user_agent: str
    
    # MongoDB
    mongo_url: str
    db_name: str
    
    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
