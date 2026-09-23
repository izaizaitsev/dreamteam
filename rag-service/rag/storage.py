import os
from io import BytesIO
from minio import Minio

def client() -> Minio:
    return Minio(os.environ.get("MINIO_ENDPOINT", "minio:9000"),
                 access_key=os.environ["MINIO_ROOT_USER"], secret_key=os.environ["MINIO_ROOT_PASSWORD"], secure=False)

def bucket_for(category: str) -> str:
    return "normative-originals" if category == "normative" else "obligation-originals"

def store_original(category: str, key: str, raw: bytes) -> None:
    storage = client()
    bucket = bucket_for(category)
    if not storage.bucket_exists(bucket):
        storage.make_bucket(bucket)
    storage.put_object(bucket, key, BytesIO(raw), len(raw), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

def read_original(category: str, key: str) -> bytes:
    response = client().get_object(bucket_for(category), key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()

