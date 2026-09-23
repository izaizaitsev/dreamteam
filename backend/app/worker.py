import os
from celery import Celery
from sqlalchemy import select
from .db import SessionLocal
from .deadlines import local_today, reminder_offset
from .models import BackgroundJob, Obligation

celery_app = Celery("legal_assistant", broker=os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672//"))

@celery_app.task(name="evaluate_deadlines", autoretry_for=(), max_retries=0)
def evaluate_deadlines(job_id: str, organization_id: str):
    try:
        with SessionLocal.begin() as db:
            job = db.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id, BackgroundJob.organization_id == organization_id).with_for_update())
            if job is None or job.status == "succeeded":
                return
            job.status = "running"
            today = local_today()
            obligations = db.scalars(select(Obligation).where(Obligation.organization_id == organization_id, Obligation.status == "open")).all()
            due = [{"id": item.id, "title": item.title, "days_remaining": (item.due_date - today).days,
                    "reminder": reminder_offset(item.due_date, today)}
                   for item in obligations if reminder_offset(item.due_date, today) is not None]
            job.result = {"due": due}
            job.status = "succeeded"
    except Exception:
        with SessionLocal.begin() as db:
            job = db.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id, BackgroundJob.organization_id == organization_id))
            if job and job.status != "succeeded":
                job.status = "failed"
                job.error = "Не удалось проверить сроки"
        raise
