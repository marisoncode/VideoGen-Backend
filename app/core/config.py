import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_env_path = os.path.join(_base_dir, ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path, override=True)

class Settings(BaseSettings):
    PROJECT_NAME: str = "MIWAY Video application"
    API_V1_STR: str = "/api/v1"
    
    # Paths
    PROJECT_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    OUTPUTS_DIR: str = os.path.join(PROJECT_ROOT, "outputs")
    TEMP_DIR: str = os.path.join(BASE_DIR, "temp")
    STORAGE_DIR: str = os.path.join(BASE_DIR, "storage")
    UPLOADS_DIR: str = os.path.join(BASE_DIR, "storage", "uploads")
    
    # API Keys
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    CLOUDFLARE_ACCOUNT_ID: str = ""
    CLOUDFLARE_API_TOKEN: str = ""
    REPLICATE_API_TOKEN: str = ""
    MAGIC_HOUR_API_KEY: str = ""

    # Default Voice
    DEFAULT_VOICE: str = "Reference Voice Clone (100% Match)"
    
    # Video Specifications
    OUTPUT_WIDTH: int = 1920
    OUTPUT_HEIGHT: int = 1080
    OUTPUT_FPS: int = 30

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

os.makedirs(settings.OUTPUTS_DIR, exist_ok=True)
os.makedirs(settings.TEMP_DIR, exist_ok=True)
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
