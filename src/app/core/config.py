from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SmartCopilot"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"

    mysql_dsn: str = "mysql+asyncmy://root:password@localhost:3306/smartcopilot"
    redis_url: str = "redis://localhost:6379/0"
    elasticsearch_url: str = "http://localhost:9200"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_file_processing_topic: str = "file-processing"
    kafka_file_processing_group_id: str = "smartcopilot-file-processing"
    upload_storage_dir: str = "storage/uploads"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_upload_bucket: str = "uploads"

    free_llm_base_url: str = ""
    free_llm_api_key: str = ""
    free_llm_model: str = ""
    paid_llm_base_url: str = ""
    paid_llm_api_key: str = ""
    paid_llm_model: str = ""
    llm_request_timeout_seconds: float = 60.0
    short_term_memory_turns: int = 8
    long_term_memory_enabled: bool = True
    long_term_memory_top_k: int = 5
    long_term_memory_extract_every_turns: int = 5
    long_term_memory_extract_window_turns: int = 10
    long_term_memory_index_name: str = "user_memories"

    embedding_provider: str = "openai-compatible"
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_dimension: int = 2048
    embedding_request_timeout_seconds: float = 60.0
    rag_chunk_size: int = 1200
    rag_chunk_overlap: int = 150
    elasticsearch_index_name: str = "document_vectors"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_seconds: int = 3600
    refresh_token_expire_seconds: int = 604800

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
