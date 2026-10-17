"""Configuration from the existing compose environment and local .env."""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


@dataclass(frozen=True)
class Settings:
    database_path: str = os.getenv("DATABASE_PATH", "app/data/appeals.sqlite3")
    storage_base_path: str = os.getenv("STORAGE_BASE_PATH", "app/data/documents")
    gigachat_key_path: str = os.getenv("GIGACHAT_AUTH_KEY_FILE", "app/data/gigachat_auth_key")
    embedding_key_path: str = os.getenv("EMBEDDING_API_KEY_FILE", "app/data/embedding_api_key")
    api_key: str = os.getenv("APP_API_KEY", "")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
    lawyer_api_key: str = os.getenv("LAWYER_API_KEY", "")
    operator_api_key: str = os.getenv("OPERATOR_API_KEY", "")
    embedding_url: str = os.getenv("EMBEDDING_API_URL", "https://foundation-models.api.cloud.ru/v1")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
    embedding_api_key: str = os.getenv("API_KEY", "")
    qdrant_url: str = os.getenv("QDRANT_BASE_URL", f"http://localhost:{os.getenv('QDRANT_HTTP_PORT', '6333')}")
    qdrant_key: str = os.getenv("QDRANT_API_KEY", "")
    retrieval_top_k: int = int(os.getenv("RAG_RETRIEVAL_TOP_K", "8"))
    gigachat_key: str = os.getenv("GIGACHAT_AUTH_KEY", "")
    gigachat_scope: str = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    gigachat_oauth_url: str = os.getenv("GIGACHAT_OAUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
    gigachat_url: str = os.getenv("GIGACHAT_API_URL", "https://api.giga.chat/v1")
    gigachat_model: str = os.getenv("GIGACHAT_MODEL", "GigaChat-2-pro")
    verify_ssl: bool = os.getenv("GIGACHAT_VERIFY_SSL", "true").lower() == "true"
    gigachat_ca_bundle_file: str = os.getenv("GIGACHAT_CA_BUNDLE_FILE", "")
    mask_pii: bool = os.getenv("LLM_MASK_PII", "false").lower() == "true"


settings = Settings()
