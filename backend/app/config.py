import logging
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"  # "development", "production", "test"

    database_url: str = "postgresql+psycopg://raguser:ragpass@localhost:5432/ragdb"
    gemini_api_key: str = ""
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://localhost,"
        "http://localhost:80"
    )

    embedding_dim: int = 768
    embedding_model: str = "gemini-embedding-001"
    embedding_batch_size: int = 32
    upload_dir: str = "uploads"
    max_upload_mb: int = 20
    max_files_per_upload: int = 10
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Generation
    generation_model: str = "gemini-3.5-flash-lite"

    # Retrieval
    retrieval_top_k: int = 5
    retrieval_score_threshold: float = 0.25
    max_context_chars: int = 8000

    # Chat
    max_history_messages: int = 10

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_jwt_secret(self):
        if self.environment == "production":
            if self.jwt_secret in ("change-me", "", "secret") or len(self.jwt_secret) < 32:
                raise ValueError(
                    "In production (ENVIRONMENT=production), JWT_SECRET must be configured with "
                    "a secure random secret of at least 32 characters."
                )
        elif self.jwt_secret == "change-me":
            log.warning(
                "Insecure default JWT_SECRET is currently in use. Set JWT_SECRET in .env for production."
            )
        return self


settings = Settings()
