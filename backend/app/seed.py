import os
from sqlalchemy import select
from .auth import password_hash
from .db import SessionLocal
from .models import Organization, User, Obligation, Prescription
from .deadlines import local_today
from datetime import timedelta

def seed():
    with SessionLocal.begin() as db:
        if db.scalar(select(Organization.id).limit(1)):
            return
        org = Organization(name="Демонстрационная управляющая организация")
        db.add(org)
        db.flush()
        for name, role in [("admin", "admin"), ("director", "director"), ("lawyer", "lawyer"), ("specialist", "specialist")]:
            db.add(User(organization_id=org.id, username=name, role=role,
                        password_hash=password_hash(os.environ.get("DEMO_PASSWORD", "demo12345"))))
        db.add(Obligation(organization_id=org.id, title="Проверить срок ответа на предписание",
                          description="Демонстрационная задача. Уточните срок по оригиналу документа.",
                          due_date=local_today() + timedelta(days=7)))
        db.add(Prescription(organization_id=org.id, title="Демонстрационное предписание",
                            content="Это учебный пример. Замените текст на фактическое предписание перед подготовкой ответа."))

if __name__ == "__main__":
    seed()
