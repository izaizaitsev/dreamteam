import hashlib
import math
import os
import re
from datetime import date
from uuid import UUID
from fastapi import FastAPI
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient, models

app = FastAPI(title="Regulatory retrieval")
COLLECTION = "regulatory_demo_hash_v1"
DIMENSION = 256

class EmbeddingProvider:
    model = "hash-v1"
    version = "1"
    dimensions = DIMENSION
    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in re.findall(r"[\w-]{3,}", text.lower()):
            digest = hashlib.sha256(word.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

embedder = EmbeddingProvider()

class RevisionIn(BaseModel):
    document_id: str
    revision_id: str
    title: str
    section: str
    source_url: str | None = None
    effective_from: date
    effective_to: date | None = None
    content: str = Field(min_length=10)

class SearchIn(BaseModel):
    question: str
    target_date: date

def client() -> QdrantClient:
    return QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"), timeout=10)

def ensure_collection(qdrant: QdrantClient) -> None:
    if not qdrant.collection_exists(COLLECTION):
        qdrant.create_collection(COLLECTION, vectors_config=models.VectorParams(size=DIMENSION, distance=models.Distance.COSINE))

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/internal/revisions")
def index_revision(data: RevisionIn):
    qdrant = client()
    ensure_collection(qdrant)
    chunks = [data.content[i:i + 1200] for i in range(0, len(data.content), 1000)]
    points = []
    for number, fragment in enumerate(chunks):
        chunk_id = str(UUID(hashlib.sha256(f"{data.revision_id}:{number}:v1".encode()).hexdigest()[:32]))
        points.append(models.PointStruct(id=chunk_id, vector=embedder.embed(fragment), payload={
            "chunk_id": chunk_id,
            "document_id": data.document_id,
            "revision_id": data.revision_id,
            "title": data.title,
            "section": data.section,
            "source_url": data.source_url,
            "effective_from": data.effective_from.isoformat(),
            "effective_to": data.effective_to.isoformat() if data.effective_to else None,
            "fragment": fragment,
            "embedding_model": embedder.model,
            "embedding_version": embedder.version,
            "indexing_version": "1",
        }))
    qdrant.upsert(collection_name=COLLECTION, points=points, wait=True)
    return {"indexed_chunks": len(points)}

@app.post("/internal/search")
def search(data: SearchIn):
    qdrant = client()
    ensure_collection(qdrant)
    day = data.target_date.isoformat()
    hits = qdrant.query_points(collection_name=COLLECTION, query=embedder.embed(data.question), limit=30)
    evidence = []
    for hit in hits.points:
        payload = hit.payload
        if hit.score < 0.08 or payload["effective_from"] > day or (payload["effective_to"] and payload["effective_to"] <= day):
            continue
        item = dict(payload)
        item["score"] = hit.score
        item["citation_id"] = f"S{len(evidence) + 1}"
        evidence.append(item)
        if len(evidence) == 5:
            break
    return {"evidence": evidence}
