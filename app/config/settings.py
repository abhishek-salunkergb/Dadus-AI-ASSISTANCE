"""Configuration module for DADUS."""
import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    """Centralized configuration for DADUS personal assistant."""
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Product Identity
    PRODUCT_NAME: str = "DADUS"
    ASSISTANT_NAME: str = "Dadus"
    WAKE_PHRASE: str = "Hey Dadus"
    USER_TITLE: str = "boss"

    # Environment & Paths
    ENVIRONMENT: str = Field(default="development", description="Environment mode (development/production/testing)")
    DATA_DIR: Path = Field(default=BASE_DIR / "data")
    LOG_DIR: Path = Field(default=BASE_DIR / "logs")
    DATABASE_URL: str = Field(default=f"sqlite:///{BASE_DIR / 'data' / 'dadus.db'}")

    # LLM Settings (OpenAI-compatible)
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="API Key for OpenAI or OpenAI-compatible provider")
    OPENAI_BASE_URL: str = Field(default="https://api.openai.com/v1", description="Base URL for OpenAI-compatible endpoint")
    LLM_MODEL: str = Field(default="gpt-4o-mini", description="Model name for reasoning and tool selection")
    LLM_TEMPERATURE: float = Field(default=0.2, ge=0.0, le=1.0)
    LLM_TIMEOUT_SECONDS: int = Field(default=30)

    # Voice / STT Settings
    STT_PROVIDER: str = Field(default="speech_recognition", description="STT Provider: speech_recognition, whisper, mock")
    STT_LANGUAGE: str = Field(default="en-US")
    STT_ENERGY_THRESHOLD: int = Field(default=300)
    STT_DYNAMIC_ENERGY_THRESHOLD: bool = Field(default=True)

    # Voice / TTS Settings
    TTS_PROVIDER: str = Field(default="sapi", description="TTS Provider: sapi (Windows native), pyttsx3, openai, mock")
    TTS_VOICE_RATE: int = Field(default=1, description="Speech rate adjustment (-10 to 10 for SAPI)")
    TTS_VOICE_VOLUME: int = Field(default=100, description="Volume 0-100")
    TTS_ENABLED: bool = Field(default=True)

    # Wake-word Settings
    WAKEWORD_PROVIDER: str = Field(default="keyword", description="Wake-word engine: keyword, mock")
    WAKEWORD_SENSITIVITY: float = Field(default=0.5)

    # Security & Permission Settings
    REQUIRE_CONFIRMATIONS: bool = Field(default=True, description="Strictly enforce confirmation on sensitive tools")
    CONFIRMATION_TIMEOUT_SECONDS: int = Field(default=60)
    ALLOWED_SEARCH_ROOTS: List[str] = Field(default_factory=lambda: [
        str(Path.home() / "Desktop"),
        str(Path.home() / "Documents"),
        str(Path.home() / "Downloads"),
        str(BASE_DIR)
    ])

    # API & UI Server
    API_HOST: str = Field(default="127.0.0.1")
    API_PORT: int = Field(default=8000)
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    # Logging
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FILE: str = Field(default=str(BASE_DIR / "logs" / "dadus.log"))

    def ensure_directories(self) -> None:
        """Ensure required data and log directories exist."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        (self.DATA_DIR / "screenshots").mkdir(parents=True, exist_ok=True)
        (self.DATA_DIR / "audio").mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_directories()
