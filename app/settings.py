"""Configuration from the existing compose environment and local .env."""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class Settings:
    database_path: str = os.getenv("DATABASE_PATH", "app/data/appeals.sqlite3")
    api_key: str = os.getenv("APP_API_KEY", "")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
    lawyer_api_key: str = os.getenv("LAWYER_API_KEY", "")
    operator_api_key: str = os.getenv("OPERATOR_API_KEY", "")
    embedding_url: str = os.getenv("EMBEDDING_BASE_URL", f"http://localhost:{os.getenv('EMBEDDING_PORT', '8080')}")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "")
    reranker_url: str = os.getenv("RERANKER_BASE_URL", f"http://localhost:{os.getenv('RERANKER_PORT', '8081')}")
    reranker_model: str = os.getenv("RERANKER_MODEL_NAME", "qwen3-reranker")
    qdrant_url: str = os.getenv("QDRANT_BASE_URL", f"http://localhost:{os.getenv('QDRANT_HTTP_PORT', '6333')}")
    qdrant_key: str = os.getenv("QDRANT_API_KEY", "")
    retrieval_top_k: int = int(os.getenv("RAG_RETRIEVAL_TOP_K", "30"))
    rerank_top_k: int = int(os.getenv("RAG_RERANK_TOP_K", "8"))
    gigachat_key: str = os.getenv("GIGACHAT_AUTH_KEY", "")
    gigachat_scope: str = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    gigachat_oauth_url: str = os.getenv("GIGACHAT_OAUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
    gigachat_url: str = os.getenv("GIGACHAT_API_URL", "https://api.giga.chat/v1")
    gigachat_model: str = os.getenv("GIGACHAT_MODEL", "GigaChat-2-pro")
    verify_ssl: bool = os.getenv("GIGACHAT_VERIFY_SSL", "true").lower() == "true"
    mask_pii: bool = os.getenv("LLM_MASK_PII", "false").lower() == "true"


settings = Settings()
