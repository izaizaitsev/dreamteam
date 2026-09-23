"""HTTP contract for the independently deployed RAG service."""
import os
import httpx

class RAGError(RuntimeError):
    def __init__(self, status_code: int = 503):
        self.status_code = status_code
        super().__init__("RAG service unavailable")

def _base() -> str:
    return os.environ.get("RAG_URL", "http://localhost:8001")

def _headers() -> dict[str, str]:
    return {"X-Internal-Token": os.environ["RAG_INTERNAL_TOKEN"]}

async def _request(method: str, path: str, *, params=None, json=None, data=None, files=None, timeout=20) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, _base() + path, headers=_headers(),
                params=params, json=json, data=data, files=files)
    except httpx.HTTPError as exc:
        raise RAGError() from exc
    if response.status_code >= 400:
        raise RAGError(response.status_code)
    return response

async def search(question: str, organization_id: str, target_date: str, categories: list[str] | None = None) -> dict:
    response = await _request("POST", "/internal/search", json={"question": question,
        "organization_id": organization_id, "as_of_date": target_date,
        "document_categories": categories or ["normative"]})
    return response.json()

async def upload_document(organization_id: str, category: str, title: str, filename: str, raw: bytes,
                          document_id: str | None = None) -> dict:
    response = await _request("POST", "/internal/documents", data={"organization_id": organization_id,
        "document_category": category, "title": title, **({"document_id": document_id} if document_id else {})},
        files={"file": (filename, raw, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, timeout=30)
    return response.json()

async def list_documents(organization_id: str, category: str | None = None) -> list[dict]:
    response = await _request("GET", "/internal/documents", params={"organization_id": organization_id,
        **({"document_category": category} if category else {})})
    return response.json()

async def get_document(organization_id: str, revision_id: str) -> dict:
    response = await _request("GET", f"/internal/documents/{revision_id}", params={"organization_id": organization_id})
    return response.json()

async def get_job(organization_id: str, job_id: str) -> dict:
    response = await _request("GET", f"/internal/jobs/{job_id}", params={"organization_id": organization_id})
    return response.json()

async def get_original(organization_id: str, revision_id: str) -> bytes:
    response = await _request("GET", f"/internal/documents/{revision_id}/original",
        params={"organization_id": organization_id}, timeout=30)
    return response.content

