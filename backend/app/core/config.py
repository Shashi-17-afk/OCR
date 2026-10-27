from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    APP_NAME: str = "Logistics OCR Service"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Ingestion & Validation Limits
    MAX_FILE_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB
    MIN_FILE_SIZE_BYTES: int = 16  # Bytes
    MAX_PDF_PAGES: int = 50
    MIN_TEXT_CHARS_PER_PAGE: int = 40
    MAX_IMAGE_DIMENSION_PX: int = 10000
    ALLOWED_EXTENSIONS: list[str] = ["pdf", "png", "jpg", "jpeg"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
