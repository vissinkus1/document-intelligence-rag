from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://raguser:ragpass@localhost:5432/ragdb"
    gemini_api_key: str = ""
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

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


settings = Settings()
