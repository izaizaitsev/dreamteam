"""AI interface used by the processing service."""
import re
from .core.settings import settings
from .schemas.ai import RequiredContext, Category, Classification, Draft
from .integrations.embedding import embed
from .integrations.vector_store import ensure_collection, delete_collection, upsert_case, retrieve
from .integrations.gigachat import GigaChatClient, gigachat_tls_verify, gigachat


def llm_text(text: str) -> str:
    if not settings.mask_pii:
        return text
    text = re.sub(r"\b[\w.-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
    text = re.sub(r"(?:\+7|8)[\s()-]*\d{3}[\s()-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}", "[ТЕЛЕФОН]", text)
    return text
