import logging
import os
import random
from datetime import date, timedelta
from celery import Celery
from sqlalchemy import select
from .db import SessionLocal
from .docx import InvalidDocx, extract
from .models import IngestionJob, Passage, Revision
from .storage import read_original
from .vector import index_passages

logger = logging.getLogger(__name__)
celery_app = Celery("rag_ingestion", broker=os.environ.get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672//"))
celery_app.conf.task_default_queue = "rag_ingestion"

def demo_dates(checksum: str, category: str, reference: date) -> tuple[date | None, date | None, date | None]:
    rng = random.Random(int(checksum[:16], 16))
    if category == "normative":
        return reference - timedelta(days=rng.randint(0, 180)), reference + timedelta(days=rng.randint(30, 365)), None
    return None, None, reference + timedelta(days=rng.randint(-10, 45))

def process_ingestion(job_id: str, revision_id: str, organization_id: str) -> None:
    with SessionLocal.begin() as db:
        job = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id,
            IngestionJob.revision_id == revision_id, IngestionJob.organization_id == organization_id).with_for_update())
        revision = db.scalar(select(Revision).where(Revision.id == revision_id,
            Revision.organization_id == organization_id).with_for_update())
        if job is None or revision is None or job.status == "succeeded":
            return
        try:
            raw = read_original(revision.category, revision.object_key)
            job.stage = "parsed"
            units = extract(raw)
            reference = revision.created_at.date()
            valid_from, valid_to, due_date = demo_dates(revision.checksum, revision.category, reference)
            passages = [Passage(revision_id=revision.id, organization_id=organization_id,
                category=revision.category, ordinal=index, section=section, fragment=fragment)
                for index, (section, fragment) in enumerate(units)]
            db.add_all(passages)
            db.flush()
            job.stage = "indexed"
            index_passages(revision, passages)
            revision.extracted_text = "\n".join(fragment for _, fragment in units)
            revision.valid_from = valid_from
            revision.valid_to = valid_to
            revision.due_date = due_date
            revision.status = "published_demo"
            job.stage = "published"
            job.status = "succeeded"
        except InvalidDocx as exc:
            revision.status = "needs_review"
            job.stage = "parsed"
            job.status = "needs_review"
            job.error_code = "invalid_docx"
            job.error_message = str(exc)
        except Exception:
            logger.exception("RAG ingestion failed for job %s", job_id)
            revision.status = "failed"
            job.status = "failed"
            job.error_code = "processing_failed"
            job.error_message = "Не удалось обработать документ"

@celery_app.task(name="rag.process_ingestion", max_retries=0)
def process_ingestion_task(envelope: dict) -> None:
    if envelope.get("schema_version") != 1 or envelope.get("kind") != "rag_ingestion":
        raise ValueError("Unsupported RAG job envelope")
    process_ingestion(envelope["job_id"], envelope["revision_id"], envelope["organization_id"])
