"""Optional derived Qdrant index. PostgreSQL remains the retrieval authority."""
import hashlib
import math
import os
import re
from qdrant_client import QdrantClient, models
from .models import Passage, Revision

COLLECTION = "rag_demo_hash_v2"
DIMENSION = 256

def embed(text: str) -> list[float]:
    vector = [0.0] * DIMENSION
    for word in re.findall(r"[\w-]{3,}", text.lower()):
        index = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big") % DIMENSION
        vector[index] += 1.0
    length = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / length for value in vector]

def index_passages(revision: Revision, passages: list[Passage]) -> None:
    qdrant = QdrantClient(url=os.environ.get("QDRANT_URL", "http://qdrant:6333"), timeout=10)
    if not qdrant.collection_exists(COLLECTION):
        qdrant.create_collection(COLLECTION, vectors_config=models.VectorParams(size=DIMENSION, distance=models.Distance.COSINE))
    qdrant.upsert(collection_name=COLLECTION, wait=True, points=[models.PointStruct(
        id=passage.id, vector=embed(passage.fragment), payload={"passage_id": passage.id,
        "revision_id": revision.id, "organization_id": revision.organization_id,
        "document_category": revision.category, "embedding_model": "hash-v1", "indexing_version": "2"})
        for passage in passages])

